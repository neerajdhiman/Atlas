"""ARQ async task definitions for training pipeline."""

import os
import uuid

from arq.connections import RedisSettings

from a1.common.logging import get_logger
from a1.common.tz import now_ist
from a1.db.engine import async_session
from a1.db.repositories import TrainingRepo
from config.settings import settings

log = get_logger("training.tasks")


async def run_training_pipeline(ctx: dict, run_id: str) -> dict:
    """Full training pipeline: collect -> build dataset -> train -> evaluate -> deploy.

    Runs as an ARQ background task.
    """
    run_uuid = uuid.UUID(run_id)

    async with async_session() as session:
        async with session.begin():
            repo = TrainingRepo(session)
            run = await repo.get_run(run_uuid)
            if not run:
                return {"error": "Training run not found"}

            await repo.update_status(run_uuid, "running", started_at=now_ist())

    try:
        # Step 1: Collect training samples
        log.info(f"[{run_id}] Collecting training samples...")
        from a1.training.collector import collect_all_conversations, collect_training_samples

        async with async_session() as session:
            samples = await collect_training_samples(
                session,
                min_quality=settings.training_min_quality,
            )
            # Fall back to all conversations if not enough quality-filtered samples
            if len(samples) < settings.training_min_samples:
                log.info(f"Only {len(samples)} quality samples, using all conversations")
                samples = await collect_all_conversations(session)

        if len(samples) < 10:
            raise ValueError(f"Not enough training samples: {len(samples)}")

        # Step 2: Build dataset
        log.info(f"[{run_id}] Building dataset from {len(samples)} samples...")
        from a1.training.dataset import build_dataset

        dataset_dir = os.path.join(settings.training_output_dir, "datasets", run_id)
        build_dataset(samples, dataset_dir)

        # Step 3: Train
        log.info(f"[{run_id}] Starting training...")
        from a1.training.trainer import run_training

        config = run.config if run else {}
        adapter_path = await run_training(
            dataset_dir=dataset_dir,
            base_model=config.get("base_model", settings.training_base_model),
            lora_rank=config.get("lora_rank", settings.training_lora_rank),
            epochs=config.get("epochs", 3),
            output_dir=os.path.join(settings.training_output_dir, "adapters", run_id),
        )

        # Step 4: Evaluate
        log.info(f"[{run_id}] Evaluating...")
        base = config.get("base_model", settings.training_base_model)

        if settings.use_harness_eval:
            from a1.training.harness_evaluator import run_harness_eval

            eval_results = run_harness_eval(
                adapter_path=adapter_path,
                base_model=base,
                tasks=config.get("eval_tasks", settings.harness_default_tasks),
            )
        else:
            from a1.training.evaluator import evaluate_model

            eval_results = await evaluate_model(
                adapter_path=adapter_path,
                test_data_path=os.path.join(dataset_dir, "test.jsonl"),
                base_model=base,
            )

        # Step 5: Deploy if improved
        log.info(f"[{run_id}] Deploying...")
        from a1.training.deployer import deploy_to_ollama

        ollama_model = await deploy_to_ollama(
            adapter_path=adapter_path,
            base_model=config.get("base_model", settings.training_base_model),
            model_name=f"run-{run_id[:8]}",
            eval_results=eval_results,
        )

        # Update run status
        async with async_session() as session:
            async with session.begin():
                repo = TrainingRepo(session)
                await repo.update_status(
                    run_uuid,
                    "completed",
                    completed_at=now_ist(),
                    metrics=eval_results,
                    artifact_path=adapter_path,
                    ollama_model=ollama_model,
                )

        result = {"status": "completed", "metrics": eval_results, "ollama_model": ollama_model}
        log.info(f"[{run_id}] Pipeline complete: {result}")
        return result

    except Exception as e:
        log.error(f"[{run_id}] Pipeline failed: {e}")
        async with async_session() as session:
            async with session.begin():
                repo = TrainingRepo(session)
                await repo.update_status(run_uuid, "failed", completed_at=now_ist())
        return {"status": "failed", "error": str(e)}


# ARQ worker settings
class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [run_training_pipeline]
    max_jobs = 1  # Only one training job at a time
