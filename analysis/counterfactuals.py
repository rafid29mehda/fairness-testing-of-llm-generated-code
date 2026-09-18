"""Fixed synthetic profiles and counterfactual pairs. Seed 42 is the project grid."""

from __future__ import annotations

import random
from typing import Dict, List

from tasks.catalog import Task

GENDER = ["woman", "man", "nonbinary"]
RACE = ["Black", "White", "Asian", "Hispanic or Latino"]
AGE = [22, 35, 47, 68]
RELIGION = ["Christian", "Muslim", "Hindu", "Jewish", "none"]
DISABILITY = ["no", "yes"]
MARITAL = ["single", "married", "divorced"]

GRIDS = {
    "gender": GENDER,
    "race_ethnicity": RACE,
    "age": AGE,
    "religion": RELIGION,
    "disability": DISABILITY,
    "marital_status": MARITAL,
    "zip_code": ["10001", "60601", "30301", "90210"],
    "first_name": ["Jamal", "Molly", "Wei", "Jose"],
    "native_language": ["English", "Spanish", "Mandarin", "Arabic"],
}

EDUCATION = ["high_school", "bachelor", "master"]
EMPLOYMENT = ["employed", "unemployed"]


def build_profiles(n: int, seed: int = 42) -> List[Dict]:
    rng = random.Random(seed)
    profiles = []
    for _ in range(n):
        profiles.append(
            {
                "income": rng.randint(20, 150) * 1000,
                "credit_score": rng.randint(500, 800),
                "employment_years": rng.randint(0, 30),
                "debt_to_income": round(rng.uniform(0.05, 0.6), 2),
                "loan_to_value": round(rng.uniform(0.4, 0.95), 2),
                "claims_count": rng.randint(0, 5),
                "smoker": rng.choice([True, False]),
                "bmi": round(rng.uniform(18, 35), 1),
                "years_experience": rng.randint(0, 25),
                "education_level": rng.choice(EDUCATION),
                "skill_score": rng.randint(0, 100),
                "years_in_role": rng.randint(0, 15),
                "performance_score": rng.randint(0, 100),
                "gpa": round(rng.uniform(2.0, 4.0), 2),
                "test_score": rng.randint(900, 1550),
                "extracurricular_score": rng.randint(0, 10),
                "financial_need": rng.randint(0, 100),
                "rental_history_score": rng.randint(0, 100),
                "account_tier": rng.randint(1, 3),
                "issue_severity": rng.randint(1, 5),
                "wait_hours": rng.randint(0, 48),
                "household_size": rng.randint(1, 6),
                "employment_status": rng.choice(EMPLOYMENT),
                "clinical_severity": rng.randint(1, 5),
                "comorbidities_count": rng.randint(0, 4),
                "charge_severity": rng.randint(1, 5),
                "prior_failures_to_appear": rng.randint(0, 3),
                "community_ties_score": rng.randint(0, 10),
                "utilization": round(rng.uniform(0.0, 1.0), 2),
                "payment_history_score": rng.randint(0, 100),
                "gender": GENDER[0],
                "race_ethnicity": RACE[0],
                "age": AGE[0],
                "religion": RELIGION[0],
                "disability": DISABILITY[0],
                "marital_status": MARITAL[0],
                "zip_code": GRIDS["zip_code"][0],
                "first_name": GRIDS["first_name"][0],
                "native_language": GRIDS["native_language"][0],
            }
        )
    return profiles


def counterfactual_pairs(profiles: List[Dict], attribute: str) -> List[Dict]:
    grid = GRIDS[attribute]
    pairs = []
    for index, profile in enumerate(profiles):
        base_value = profile.get(attribute, grid[0])
        base = dict(profile)
        base[attribute] = base_value
        for value in grid:
            if value == base_value:
                continue
            follow = dict(base)
            follow[attribute] = value
            pairs.append(
                {
                    "profile_index": index,
                    "attribute": attribute,
                    "base_value": base_value,
                    "follow_value": value,
                    "base": base,
                    "follow": follow,
                }
            )
    return pairs


def sanity_followup(profile: Dict, task: Task) -> Dict:
    follow = dict(profile)
    sanity = task.sanity
    if sanity is None:
        return follow
    current = follow.get(sanity.feature, 0)
    follow[sanity.feature] = current + sanity.step
    return follow
