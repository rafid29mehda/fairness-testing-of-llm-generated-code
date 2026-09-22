"""The full-run job list matches the 1,680-call budget."""

from analysis.study import generation_id, planned_jobs


def test_one_model_has_560_jobs():
    task_ids = [f"task_{index}" for index in range(16)]
    jobs = planned_jobs(task_ids, 5)
    assert len(jobs) == 560
    assert len({generation_id("openai/gpt-oss-20b", job["task"], job["variant"], job["sample_index"]) for job in jobs}) == 560


def test_three_models_match_the_plan_budget():
    task_ids = [f"task_{index}" for index in range(16)]
    assert len(planned_jobs(task_ids, 5)) * 3 == 1680
