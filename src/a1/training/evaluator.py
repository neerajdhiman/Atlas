"""Evaluate fine-tuned models against their base versions."""

import json

from a1.common.logging import get_logger

log = get_logger("training.evaluator")


async def evaluate_model(
    adapter_path: str,
    test_data_path: str,
    base_model: str,
    max_samples: int = 100,
) -> dict:
    """Compare fine-tuned model against base model on test data.

    Returns dict with evaluation metrics.
    """
    log.info(f"Evaluating adapter at {adapter_path} against base {base_model}")

    import torch
    from peft import PeftModel

    from config.settings import settings

    if settings.use_unsloth:
        # Faster model loading via Unsloth
        from unsloth import FastLanguageModel

        base, tokenizer = FastLanguageModel.from_pretrained(
            model_name=base_model,
            load_in_4bit=True,
            max_seq_length=2048,
        )
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        base = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load fine-tuned
    finetuned = PeftModel.from_pretrained(base, adapter_path)

    # Load test samples
    samples = []
    with open(test_data_path, "r") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    samples = samples[:max_samples]

    base_scores = []
    ft_scores = []

    for sample in samples:
        messages = sample["messages"]
        # Build prompt from all but last assistant message
        prompt_msgs = []
        expected = ""
        for msg in messages:
            if msg["role"] == "assistant":
                expected = msg["content"]
            else:
                prompt_msgs.append(msg)

        if not expected or not prompt_msgs:
            continue

        prompt_text = tokenizer.apply_chat_template(
            prompt_msgs, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=1024)
        inputs = {k: v.to(base.device) for k, v in inputs.items()}

        with torch.no_grad():
            base_out = base(**inputs, labels=inputs["input_ids"])
            base_scores.append(base_out.loss.item())

            ft_out = finetuned(**inputs, labels=inputs["input_ids"])
            ft_scores.append(ft_out.loss.item())

    avg_base_loss = sum(base_scores) / max(len(base_scores), 1)
    avg_ft_loss = sum(ft_scores) / max(len(ft_scores), 1)
    improvement = (avg_base_loss - avg_ft_loss) / max(avg_base_loss, 0.001)

    results = {
        "base_model": base_model,
        "adapter_path": adapter_path,
        "test_samples": len(samples),
        "avg_base_loss": round(avg_base_loss, 4),
        "avg_finetuned_loss": round(avg_ft_loss, 4),
        "improvement": round(improvement, 4),
        "improved": improvement > 0,
    }
    log.info(
        f"Eval results: base_loss={avg_base_loss:.4f}, ft_loss={avg_ft_loss:.4f}, "
        f"improvement={improvement:.2%}"
    )
    return results
