"""Shared formal research entry for legacy CLI users."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiment.run_experiment import main

if __name__=='__main__':main()
