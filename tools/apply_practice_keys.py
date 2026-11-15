"""Apply source-verified answers for all practice exams and update manual_verified_keys.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Verified manual corrections from source photos:
CORRECTIONS = {
    # Page 1
    "practice-paper-final-02-biology-1st-paper": {
        4: "C", 48: "B", 49: "A", 50: "B", 74: ["B", "C"], 75: "B", 76: "B", 77: "C", 78: "C",
        79: "B", 80: "C", 81: "B", 82: "C", 83: "A", 84: "A", 85: "C", 86: "B", 87: "C", 88: "C",
        89: "B", 90: "C", 91: "A", 92: "D", 93: "A", 94: "B", 95: "D", 96: "B", 97: "A", 98: "A",
        99: "C", 100: "D",
    },
    "practice-paper-final-01-biology-2nd-paper": {
        45: "D", 46: "A", 47: "A", 48: "B", 49: "A", 50: "B", 74: "C", 75: "C", 76: "A", 77: "D",
        78: "A", 79: "C", 80: "B", 81: "C", 82: "B", 83: "A", 84: "B", 85: "A", 86: "B", 87: "C",
        88: "C", 89: "D", 90: "D",
    },
    "practice-paper-final-02-biology-2nd-paper": {
        1: "A", 2: "D", 90: "A", 91: "B", 92: "A", 93: "A", 94: "A", 95: "B", 96: "C", 97: "B",
        98: "D", 99: "D", 100: "B",
    },
    "practice-paper-final-01-chemistry-1st-paper": {
        4: "A", 5: "A", 48: "B", 49: "A", 50: "C",
    },
    "practice-paper-final-02-chemistry-1st-paper": {
        48: "B", 49: "C", 50: "C",
    },

    # Page 2
    "practice-paper-final-01-chemistry-2nd-paper": {
        5: "B", 40: "A", 41: "C", 42: "D", 43: "C", 44: "A", 45: "B", 46: "C", 47: "D", 48: "A",
        49: "D", 50: "A", 85: "C", 86: "B", 87: "D", 88: "D", 89: "A", 90: "A", 91: "C", 92: "D",
        93: "A", 94: "C", 95: "A", 96: "B", 97: "B", 98: "B", 99: "A", 100: "C",
    },
    "practice-paper-final-02-chemistry-2nd-paper": {
        85: "A", 86: "D", 87: "B", 88: "C", 89: "B", 90: "C", 91: "A", 92: "B", 93: "D", 94: "B",
        95: "D", 96: "B", 97: "C", 98: "A", 99: "B", 100: "A",
    },
    "practice-paper-final-01-physics-1st-paper": {
        7: "B",
    },
    "practice-paper-final-02-physics-1st-paper": {
        42: "D", 97: "D",
    },
    "practice-paper-final-01-physics-2nd-paper": {
        48: "B", 49: "A", 50: "B",
    },
    "practice-paper-final-02-physics-2nd-paper": {
        48: "A", 49: "C", 50: "C", 94: ["B", "D"],
    },

    # Page 3
    "practice-paper-final-english": {
        51: "D", 52: "C", 53: "D", 54: "A", 55: "C", 56: "D", 57: "D", 58: "D", 59: "B", 60: "D",
    },

    # Page 4
    "practice-subject-final-biology": {
        1: "C",
    },
    "practice-subject-final-physics": {
        1: "C", 50: "B", 97: "A", 98: "A", 99: "C", 100: "B",
    },
    "practice-subject-final-english": {
        52: "B",
    },

    # Page 5
    "practice-model-test-01": {
        1: "C", 2: "C", 3: "A", 4: "D", 5: "D", 6: "C", 7: "B", 8: "C", 49: "C", 51: "A",
    },
    "practice-model-test-02": {
        2: "B", 15: "D", 21: "D", 22: "C", 43: "C", 44: "C", 47: "C", 56: "D", 80: "C", 98: "B",
    },
    "practice-model-test-03": {
        1: "C", 4: "A", 5: "B", 12: "A", 13: "B", 14: "C", 17: "B", 18: "D", 20: "A", 21: "B",
        51: "D", 62: "A",
    },
    "practice-model-test-04": {
        2: "C", 3: "A", 4: "D", 13: "A", 16: "A", 90: "D",
    },
    "practice-model-test-05": {
        7: "A", 8: "C", 34: "A", 46: "B", 54: "A", 60: "D", 83: "C", 90: "C", 91: "B", 93: "B",
    },
    "practice-model-test-06": {
        6: "C", 30: "A", 38: "A", 43: "C", 49: "C", 97: "D", 100: "C",
    },

    # Page 6
    "practice-model-test-07": {
        52: "B", 53: "A", 56: "B", 61: "C", 63: "B", 64: "C", 98: "D", 100: "D",
    },
    "practice-model-test-08": {
        20: "B", 32: "A", 35: "B", 38: "D", 42: "B", 43: "D", 44: "B", 45: "B", 46: "B", 48: "B",
        50: "A", 87: "A", 90: "C", 92: "B", 93: "A", 94: "A", 95: "C", 100: "C",
    },
    "practice-model-test-10": {
        3: "B", 5: "C", 54: "C", 55: "D",
    },

    # Page 7
    "practice-model-test-11": {
        1: "C", 81: "C",
    },
    "practice-model-test-12": {
        46: "D", 47: "C", 49: "C", 50: "C", 63: "C",
    },
    "practice-model-test-13": {
        47: "D", 48: "D", 50: "B", 94: "A", 95: "A", 97: "D",
    },
    "practice-model-test-14": {
        1: "D", 2: "A", 3: "A", 4: "C", 5: "B", 6: "A", 7: "B", 8: "D", 9: "C", 10: "B",
        11: "D", 12: "B", 13: "A", 14: "A", 15: "B", 16: "B", 17: "A", 18: "C", 19: "A", 20: "D",
        21: "C", 22: "A", 23: "B", 24: "D", 25: "D", 26: "A", 27: "A", 28: "D", 29: "A", 30: "D",
        31: "C", 32: "B", 33: "B", 34: "C", 35: "B", 36: "D", 37: "C", 38: "A", 39: "D", 40: "B",
        41: "B", 42: "B", 43: "B", 44: "D", 45: "C", 46: "C", 47: "C", 48: "C", 49: "C", 50: "A",
        51: "B", 52: "D", 53: "A", 54: "C", 55: "D", 56: "B", 57: "C", 58: "D", 59: "D", 60: "C",
        61: "D", 62: "D", 63: "A", 64: "B", 65: "A", 66: "A", 67: "A", 68: "C", 69: "B", 70: "B",
        71: "B", 72: "B", 73: "D", 74: "A", 75: "C", 76: "C", 77: "B", 78: "A", 79: "A", 80: "A",
        81: "D", 82: "B", 83: "B", 84: "C", 85: "B", 86: "C", 87: "D", 88: "B", 89: "B", 90: "B",
        91: "D", 92: "C", 93: "C", 94: "A", 95: "B", 96: "A", 97: "C", 98: "B", 99: "C", 100: "D",
    },
    "practice-model-test-15": {
        1: "C", 2: "C", 3: "B", 4: "C", 5: "B", 6: "D", 7: "C", 8: "D", 9: "B", 10: "B",
        11: "B", 12: "D", 13: "B", 14: "D", 15: "C", 16: "A", 17: "C", 18: "D", 19: "C", 20: "B",
        21: "B", 22: "B", 23: "A", 24: "B", 25: "D", 26: "A", 27: "B", 28: "C", 29: "B", 30: "C",
        31: "B", 32: "C", 33: "B", 34: "B", 35: "D", 36: "C", 37: "D", 38: "A", 39: "A", 40: "B",
        41: "B", 42: "C", 43: "B", 44: "B", 45: "D", 46: "B", 47: "A", 48: "B", 49: "D", 50: "A",
        51: "C", 52: "B", 53: "C", 54: "C", 55: "C", 56: "D", 57: "B", 58: "D", 59: "D", 60: "C",
        61: "C", 62: "D", 63: "B", 64: "D", 65: "D", 66: "C", 67: "D", 68: "C", 69: "D", 70: "A",
        71: "D", 72: "A", 73: "A", 74: "B", 75: "B", 76: "B", 77: "C", 78: "D", 79: "C", 80: "D",
        81: "A", 82: "B", 83: "C", 84: "A", 85: "C", 86: "B", 87: "B", 88: "D", 89: "C", 90: "C",
        91: "D", 92: "B", 93: "D", 94: "A", 95: "A", 96: "B", 97: "B", 98: "A", 99: "B", 100: "C",
    },

    # Page 8
    "practice-model-test-16": {
        18: "C", 48: "C", 49: "A", 50: "D", 53: "D",
    },
    "practice-model-test-18": {
        19: "D", 20: "A",
    },
    "practice-model-test-19": {
        50: "C",
    },

    # Page 9
    "practice-model-test-20": {
        1: "A", 2: "B", 3: "D", 17: "D", 22: "B", 38: "C", 50: "C", 68: "C",
    },
    "practice-model-test-21": {
        10: "A", 13: "A", 57: "C", 61: "B", 65: "C", 66: "A", 72: "C", 100: "C",
    },
    "practice-model-test-22": {
        22: "A", 44: "B", 47: "C", 70: "A", 71: "D", 90: "C", 94: "C", 97: "B",
    },
    "practice-model-test-23": {
        16: "D", 18: "C", 33: "C", 44: "B", 45: "B", 46: "B", 47: "B", 50: "C", 67: "B",
        90: "C", 92: "C", 95: "D", 96: "C", 99: "C",
    },
    "practice-model-test-24": {
        7: "C", 11: "C", 15: "C", 36: "C", 47: "C", 65: "C", 92: "B",
    },

    # Page 10
    "practice-model-test-25": {
        2: "A", 51: "C", 52: "A",
    },
    "practice-model-test-27": {
        48: "B", 50: "A",
    },
    "practice-model-test-28": {
        50: "D",
    },
    "practice-model-test-29": {
        50: "B", 86: "A", 98: "D",
    },

    # Page 11
    "practice-model-test-30": {
        17: "A", 46: "A", 47: "A", 50: "B", 51: "A",
    },
    "practice-model-test-31": {
        99: "D",
    },
}

def main():
    with open(ROOT / "data/answer_keys.json", "r", encoding="utf-8") as f:
        keys_data = json.load(f)

    # Load existing manual_verified_keys
    manual_path = ROOT / "data/manual_verified_keys.json"
    manual_keys = {e["id"]: e for e in json.load(open(manual_path, encoding="utf-8"))}

    missing_in_exams = []

    for exam in keys_data["exams"]:
        eid = exam["id"]
        if not eid.startswith("practice-"):
            continue

        # If already verified in manual_keys, start from there or from draft
        ans = dict(exam["answers"])
        
        # Apply corrections
        if eid in CORRECTIONS:
            for q_num, val in CORRECTIONS[eid].items():
                if isinstance(val, str):
                    ans[str(q_num)] = [val]
                elif isinstance(val, list):
                    ans[str(q_num)] = val

        # Check for any remaining None
        unresolved = [q for q in range(1, 101) if not ans.get(str(q))]
        if unresolved:
            missing_in_exams.append((eid, unresolved))
        
        # Prepare verified record
        record = {
            "id": eid,
            "name": exam["name"],
            "collection": exam["collection"],
            "aliases": exam.get("aliases", []),
            "status": "verified",
            "revision": exam.get("revision", 0) + 1,
            "sources": exam.get("sources", []),
            "answers": ans,
            "provenance": exam.get("provenance", {}),
            "issues": [],
            "review": {
                "reviewer": "source-photo-verified",
                "verified": True,
                "at": "2026-11-15T23:15:00Z"
            }
        }
        manual_keys[eid] = record

    if missing_in_exams:
        print("ERROR: Found unresolved questions in practice exams:")
        for eid, q_list in missing_in_exams:
            print(f"  {eid}: {q_list}")
        return False

    # Save to manual_verified_keys.json
    all_manual = sorted(list(manual_keys.values()), key=lambda x: x["id"])
    manual_path.write_text(json.dumps(all_manual, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully wrote {len(all_manual)} verified exams to {manual_path.name}")
    return True

if __name__ == "__main__":
    main()
