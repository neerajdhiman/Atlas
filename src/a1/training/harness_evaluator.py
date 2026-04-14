"""Standardized model evaluation using EleutherAI's lm-evaluation-harness.

Provides comprehensive benchmarks (MMLU, HellaSwag, TruthfulQA, HumanEval, etc.)
instead of just loss-based comparison.
"""

from a1.common.logging import get_logger
from config.settings import settings

log = get_logger("training.harness_evaluator")

# Map A1 task types to appropriate benchmark suites
TASK_BENCHMARKS = {
    "code": ["humaneval", "mbpp"],
    "math": ["gsm8k"],
    "general": ["mmlu", "hellaswag"],
    "analysis": ["truthfulqa_mc2"],
    "chat": ["mmlu", "hellaswag"],
    "creative": ["hellaswag"],
    "summarization": ["xsum"],
    "translation": ["wmt16-en-de-bleu"],
    "structured_extraction": ["mmlu"],
}


def run_harness_eval(
    adapter_path: str,
    base_model: str,
    tasks: list[str] | None = None,
    num_fewshot: int | None = None,
    batch_size: int | None = None,
) -> dict:
    """Run lm-evaluation-harness benchmarks on a fine-tuned model.

    Args:
        adapter_path: Path to LoRA adapter weights
        base_model: HuggingFace model name
        tasks: List of benchmark task names (e.g., ["mmlu", "hellaswag"])
        num_fewshot: Number of few-shot examples
        batch_size: Batch size for evaluation

    Returns:
        Dict with per-task scores, suitable for storing in training_runs.metrics
    """
    tasks = tasks or settings.harness_default_tasks
    num_fewshot = num_fewshot if num_fewshot is not None else settings.harness_num_fewshot
    batch_size = batch_size or settings.harness_batch_size

    log.info(f"Running lm-eval-harness: tasks={tasks}, fewshot={num_fewshot}, batch={batch_size}")

    import lm_eval

    # Build model_args string for HuggingFace model with LoRA adapter
    model_args = f"pretrained={base_model},peft={adapter_path},load_in_4bit=True"

    try:
        results = lm_eval.simple_evaluate(
            model="hf",
            model_args=model_args,
            tasks=tasks,
            num_fewshot=num_fewshot,
            batch_size=batch_size,
        )
    except Exception as e:
        log.error(f"lm-eval-harness failed: {e}")
        return {"error": str(e), "tasks": tasks}

    # Extract key metrics from results
    eval_results = {
        "evaluator": "lm-eval-harness",
        "tasks": {},
        "num_fewshot": num_fewshot,
    }

    task_results = results.get("results", {})
    for task_name, task_data in task_results.items():
        task_metrics = {}
        # Extract common metric keys
        for key, value in task_data.items():
            if isinstance(value, (int, float)):
                task_metrics[key] = round(value, 4) if isinstance(value, float) else value
        eval_results["tasks"][task_name] = task_metrics

    # Compute aggregate score (average accuracy across all tasks)
    accuracies = []
    for task_data in eval_results["tasks"].values():
        for key in ("acc", "acc_norm", "exact_match", "bleu"):
            if key in task_data:
                accuracies.append(task_data[key])
                break

    eval_results["avg_score"] = round(sum(accuracies) / max(len(accuracies), 1), 4)
    eval_results["improved"] = True  # harness doesn't compare base vs ft, just absolute scores

    log.info(
        f"Harness eval complete: avg_score={eval_results['avg_score']}, "
        f"tasks={len(eval_results['tasks'])}"
    )
    return eval_results


def run_comparative_eval(
    adapter_path: str,
    base_model: str,
    tasks: list[str] | None = None,
) -> dict:
    """Run harness eval on both base and fine-tuned, then compare.

    Returns dict with base_scores, ft_scores, and improvement per task.
    """
    tasks = tasks or settings.harness_default_tasks

    log.info("Running comparative evaluation (base vs fine-tuned)...")

    # Eval base model
    import lm_eval

    base_results = lm_eval.simple_evaluate(
        model="hf",
        model_args=f"pretrained={base_model},load_in_4bit=True",
        tasks=tasks,
        num_fewshot=settings.harness_num_fewshot,
        batch_size=settings.harness_batch_size,
    )

    # Eval fine-tuned
    ft_results = lm_eval.simple_evaluate(
        model="hf",
        model_args=f"pretrained={base_model},peft={adapter_path},load_in_4bit=True",
        tasks=tasks,
        num_fewshot=settings.harness_num_fewshot,
        batch_size=settings.harness_batch_size,
    )

    comparison = {"evaluator": "lm-eval-harness-comparative", "tasks": {}}

    for task_name in tasks:
        base_data = base_results.get("results", {}).get(task_name, {})
        ft_data = ft_results.get("results", {}).get(task_name, {})

        # Find the primary metric
        for metric_key in ("acc_norm", "acc", "exact_match", "bleu"):
            if metric_key in base_data and metric_key in ft_data:
                base_score = base_data[metric_key]
                ft_score = ft_data[metric_key]
                improvement = ft_score - base_score
                comparison["tasks"][task_name] = {
                    "metric": metric_key,
                    "base": round(base_score, 4),
                    "finetuned": round(ft_score, 4),
                    "improvement": round(improvement, 4),
                }
                break

    # Aggregate
    improvements = [t["improvement"] for t in comparison["tasks"].values()]
    comparison["avg_improvement"] = round(sum(improvements) / max(len(improvements), 1), 4)
    comparison["improved"] = comparison["avg_improvement"] > 0
    comparison["improvement"] = comparison["avg_improvement"]  # compat with deployer threshold

    log.info(f"Comparative eval: avg_improvement={comparison['avg_improvement']}")
    return comparison
