"""Deploy fine-tuned models to Ollama for serving."""

import os
import subprocess
import tempfile

import httpx

from a1.common.logging import get_logger
from config.settings import settings

log = get_logger("training.deployer")

DEPLOY_THRESHOLD = 0.02  # 2% improvement required to deploy


async def deploy_to_ollama(
    adapter_path: str,
    base_model: str,
    model_name: str,
    eval_results: dict,
) -> str | None:
    """Merge adapter, convert to GGUF, and register with Ollama.

    Returns the Ollama model name if deployed, None if skipped.
    """
    if eval_results.get("improvement", 0) < DEPLOY_THRESHOLD:
        log.info(f"Improvement {eval_results['improvement']:.2%} below threshold, skipping deploy")
        return None

    log.info(f"Deploying {model_name} to Ollama...")

    # Step 1: Merge adapter and convert to GGUF
    gguf_path = os.path.join(settings.training_output_dir, "gguf", f"{model_name}.gguf")
    os.makedirs(os.path.dirname(gguf_path), exist_ok=True)
    merged_path = os.path.join(settings.training_output_dir, "merged", model_name)
    os.makedirs(merged_path, exist_ok=True)

    if settings.use_unsloth:
        # Unsloth: native GGUF export (fast, reliable)
        log.info("Using Unsloth for merge + GGUF export...")
        try:
            from unsloth import FastLanguageModel

            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=base_model, load_in_4bit=True, max_seq_length=2048,
            )
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter_path)

            model.save_pretrained_gguf(gguf_path, tokenizer, quantization_method="q4_k_m")
            log.info(f"Unsloth GGUF export complete: {gguf_path}")
        except Exception as e:
            log.warning(f"Unsloth GGUF export failed: {e}, falling back to legacy")
            gguf_path = None
    else:
        # Legacy: manual merge + llama.cpp conversion
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        log.info("Merging adapter weights (legacy)...")
        base = AutoModelForCausalLM.from_pretrained(base_model, device_map="cpu", trust_remote_code=True)
        model = PeftModel.from_pretrained(base, adapter_path)
        merged = model.merge_and_unload()
        merged.save_pretrained(merged_path)

        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        tokenizer.save_pretrained(merged_path)
        log.info(f"Merged model saved to {merged_path}")

        try:
            subprocess.run(
                ["python", "-m", "llama_cpp.convert", merged_path, "--outfile", gguf_path, "--outtype", "q4_0"],
                check=True, capture_output=True, text=True,
            )
            log.info(f"GGUF conversion complete: {gguf_path}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.warning(f"GGUF conversion failed: {e}")
            gguf_path = None

    # Step 3: Create Ollama Modelfile and register
    ollama_model_name = f"a1-{model_name}"

    if gguf_path and os.path.exists(gguf_path):
        modelfile_content = f'FROM {gguf_path}\nSYSTEM "You are a helpful assistant fine-tuned by A1 Trainer."'
    else:
        # Try using the merged safetensors path directly
        modelfile_content = f'FROM {merged_path}\nSYSTEM "You are a helpful assistant fine-tuned by A1 Trainer."'

    with tempfile.NamedTemporaryFile(mode="w", suffix=".Modelfile", delete=False) as f:
        f.write(modelfile_content)
        modelfile_path = f.name

    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=600.0) as client:
            resp = await client.post("/api/create", json={
                "name": ollama_model_name,
                "modelfile": modelfile_content,
            })
            if resp.status_code == 200:
                log.info(f"Registered Ollama model: {ollama_model_name}")
                return ollama_model_name
            else:
                log.error(f"Ollama registration failed: {resp.text}")
                return None
    except Exception as e:
        log.error(f"Failed to register with Ollama: {e}")
        return None
    finally:
        os.unlink(modelfile_path)
