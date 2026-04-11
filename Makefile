PYTHON ?= python3
PHASE7_MODE ?= local-full
PHASE7_RENDER ?= false

.PHONY: run_jd_eval run_selection_eval run_e2e_eval run_red_team_eval run_all_phase7

run_jd_eval:
	PYTHONPATH=.:src $(PYTHON) scripts/run_phase7.py run_jd_eval --mode $(PHASE7_MODE)

run_selection_eval:
	PYTHONPATH=.:src $(PYTHON) scripts/run_phase7.py run_selection_eval --mode $(PHASE7_MODE)

run_e2e_eval:
	PYTHONPATH=.:src $(PYTHON) scripts/run_phase7.py run_e2e_eval --mode $(PHASE7_MODE) --enable-render $(PHASE7_RENDER)

run_red_team_eval:
	PYTHONPATH=.:src $(PYTHON) scripts/run_phase7.py run_red_team_eval --mode $(PHASE7_MODE)

run_all_phase7:
	PYTHONPATH=.:src $(PYTHON) scripts/run_phase7.py run_all_phase7 --mode $(PHASE7_MODE) --enable-render $(PHASE7_RENDER)
