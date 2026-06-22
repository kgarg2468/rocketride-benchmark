"""Real LangChain competitor processes (run as isolated subprocesses; see lc_bench.py).

NOT part of RocketRide — this is bench scaffolding ("ours"), the measured stand-in for the
"≈ LangChain" stdlib proxies the suite used to ship. See harness/lc_baselines.py for the
fairness seam (same mock + same busy() loop both sides).
"""
