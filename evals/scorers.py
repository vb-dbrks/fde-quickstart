"""Custom scorers. The built-in LLM judges (Correctness, Safety, ...) are set up in evals/run.py."""

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

MAX_WORDS = 120


@scorer
def concise(outputs: str) -> Feedback:
    """Deterministic check that answers stay short enough to read in the app."""
    words = len(str(outputs).split())
    return Feedback(value=words <= MAX_WORDS, rationale=f"{words} words (limit {MAX_WORDS})")
