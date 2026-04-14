"""QLoRA fine-tuning orchestrator.

Supports two backends:
- Unsloth (default, 2-5x faster): use_unsloth=True
- HuggingFace manual (legacy): use_unsloth=False
"""

import os
from pathlib import Path

from a1.common.logging import get_logger
from config.settings import settings

log = get_logger("training.trainer")


async def run_training(
    dataset_dir: str,
    base_model: str | None = None,
    lora_rank: int | None = None,
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    output_dir: str | None = None,
) -> str:
    """Run QLoRA fine-tuning. Returns path to saved adapter weights."""
    base_model = base_model or settings.training_base_model
    lora_rank = lora_rank or settings.training_lora_rank
    output_dir = output_dir or os.path.join(settings.training_output_dir, "adapters", "latest")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if settings.use_unsloth:
        return await _train_unsloth(
            dataset_dir, base_model, lora_rank, epochs, batch_size, learning_rate, output_dir
        )
    else:
        return await _train_hf_legacy(
            dataset_dir, base_model, lora_rank, epochs, batch_size, learning_rate, output_dir
        )


async def _train_unsloth(
    dataset_dir: str,
    base_model: str,
    lora_rank: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    output_dir: str,
) -> str:
    """Unsloth-backed training (2-5x faster, lower VRAM)."""
    log.info(
        f"Starting Unsloth QLoRA training: base={base_model}, rank={lora_rank}, epochs={epochs}"
    )

    from datasets import load_dataset
    from transformers import TrainingArguments
    from trl import SFTTrainer
    from unsloth import FastLanguageModel

    # Load model + tokenizer via Unsloth (handles quantization automatically)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=2048,
        load_in_4bit=True,
        dtype=None,  # auto-detect
    )

    # Apply LoRA via Unsloth (optimized kernel patching)
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_rank,
        lora_alpha=lora_rank * 2,
        lora_dropout=0.05,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",  # Unsloth's optimized checkpointing
    )

    # Load + format dataset (same as legacy)
    train_ds = load_dataset(
        "json", data_files=os.path.join(dataset_dir, "train.jsonl"), split="train"
    )
    val_ds = load_dataset("json", data_files=os.path.join(dataset_dir, "val.jsonl"), split="train")

    def format_chat(example):
        text = tokenizer.apply_chat_template(example["messages"], tokenize=False)
        return {"text": text}

    train_ds = train_ds.map(format_chat)
    val_ds = val_ds.map(format_chat)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        warmup_ratio=0.1,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        bf16=True,
        report_to="none",
        optim="adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        dataset_text_field="text",
        max_seq_length=2048,
    )

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    log.info(f"Unsloth training complete. Adapter saved to {output_dir}")
    return output_dir


async def _train_hf_legacy(
    dataset_dir: str,
    base_model: str,
    lora_rank: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    output_dir: str,
) -> str:
    """Legacy HuggingFace manual QLoRA training."""
    log.info(
        f"Starting HF legacy QLoRA training: base={base_model}, rank={lora_rank}, epochs={epochs}"
    )

    import torch
    from datasets import load_dataset
    from peft import LoraConfig, TaskType, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from trl import SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=lora_rank,
        lora_alpha=lora_rank * 2,
        lora_dropout=0.05,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )

    train_ds = load_dataset(
        "json", data_files=os.path.join(dataset_dir, "train.jsonl"), split="train"
    )
    val_ds = load_dataset("json", data_files=os.path.join(dataset_dir, "val.jsonl"), split="train")

    def format_chat(example):
        text = tokenizer.apply_chat_template(example["messages"], tokenize=False)
        return {"text": text}

    train_ds = train_ds.map(format_chat)
    val_ds = val_ds.map(format_chat)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        warmup_ratio=0.1,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        bf16=True,
        report_to="none",
        optim="paged_adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        peft_config=peft_config,
        dataset_text_field="text",
        max_seq_length=2048,
    )

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    log.info(f"HF legacy training complete. Adapter saved to {output_dir}")
    return output_dir
