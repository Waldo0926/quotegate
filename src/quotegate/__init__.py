"""quotegate: let a language model answer only with sentences copied from your passages, checked in code."""
from .core import Dropped, Passage, Quote, Result, Rules, check, judge, parse, sentence

__version__ = "0.1.0"
__all__ = ["Dropped", "Passage", "Quote", "Result", "Rules", "__version__", "check", "judge", "parse", "sentence"]
