#C:\Users\504\3D Objects\biohealth4\mbti_test.py
"""12문항으로 진행하는 간이 MBTI 성향 검사 (표준 라이브러리만 사용)"""

from typing import Dict, List, Optional

OPTIONS = {
    1: "전혀 그렇지 않다",
    2: "별로 그렇지 않다",
    3: "대체로 그렇다",
    4: "매우 그렇다",
}

# 각 축마다 3문항씩 배정했습니다. 모든 문항은 첫 번째 글자(E/S/T/J)에
# 동의할수록 높은 점수가 되도록 작성했습니다.
QUESTIONS: List[Dict[str, str]] = [
    {
        "axis": "EI",
        "text": "처음 만난 사람들과 함께 있을 때 먼저 말을 걸거나 대화를 이어가는 편이다.",
        "explanation": "낯선 모임에서 먼저 교류하는 편인지, 관찰하며 익숙해진 뒤 대화하는 편인지 살펴봅니다.",
    },
    {
        "axis": "SN",
        "text": "설명이나 계획을 들을 때 큰 그림보다 구체적인 사실과 실제 사례가 먼저 궁금하다.",
        "explanation": "관찰 가능한 세부 정보와 경험을 먼저 보는 경향(S)인지, 전체적인 의미와 가능성을 먼저 보는 경향(N)인지 살펴봅니다.",
    },
    {
        "axis": "TF",
        "text": "의견이 다를 때 개인적인 호감보다 공정한 기준과 논리적 일관성을 우선해 판단하는 편이다.",
        "explanation": "판단할 때 원칙과 논리를 중시하는 경향(T)인지, 사람과 상황에 미치는 영향을 중시하는 경향(F)인지 살펴봅니다.",
    },
    {
        "axis": "JP",
        "text": "일정이 정해지면 미리 계획을 세우고, 진행 상황과 완료 여부를 확인하는 편이다.",
        "explanation": "계획과 구조를 미리 정해 두는 경향(J)인지, 진행하면서 유연하게 조정하는 경향(P)인지 살펴봅니다.",
    },
    {
        "axis": "EI",
        "text": "생각을 정리할 때 혼자 오래 생각하기보다 다른 사람과 이야기하며 정리하는 편이다.",
        "explanation": "대화와 상호작용을 통해 생각을 정리하는 경향(E)인지, 혼자 숙고한 뒤 생각을 나누는 경향(I)인지 살펴봅니다.",
    },
    {
        "axis": "SN",
        "text": "새로운 일을 배울 때 추상적인 원리보다 구체적인 절차를 직접 해보는 것이 더 편하다.",
        "explanation": "실제 사례와 단계별 경험을 통해 배우는 경향(S)인지, 먼저 개념과 원리를 이해하려는 경향(N)인지 살펴봅니다.",
    },
    {
        "axis": "TF",
        "text": "갈등 상황에서는 당사자들의 감정보다 원칙과 공정성을 먼저 따져보는 편이다.",
        "explanation": "갈등을 다룰 때 일관된 기준을 우선하는 경향(T)인지, 관계와 사람들의 감정을 우선 고려하는 경향(F)인지 살펴봅니다.",
    },
    {
        "axis": "JP",
        "text": "마감 직전에 서두르기보다 미리 준비를 끝내고 여유를 두는 것이 마음 편하다.",
        "explanation": "일을 일찍 정리하고 마무리하려는 경향(J)인지, 마감까지 선택지를 열어 두고 유연하게 진행하는 경향(P)인지 살펴봅니다.",
    },
    {
        "axis": "EI",
        "text": "모임에서는 소수와 오래 대화하기보다 여러 사람과 폭넓게 이야기하는 것이 편하다.",
        "explanation": "여러 사람과 활발히 교류하는 경향(E)인지, 소수와 깊이 이야기하거나 혼자 쉬는 시간을 선호하는 경향(I)인지 살펴봅니다.",
    },
    {
        "axis": "SN",
        "text": "무언가를 판단할 때 지금 확인할 수 있는 정보와 과거의 경험을 주된 근거로 삼는 편이다.",
        "explanation": "검증 가능한 사실과 경험을 중시하는 경향(S)인지, 정보 사이의 패턴이나 앞으로의 가능성도 함께 보는 경향(N)인지 살펴봅니다.",
    },
    {
        "axis": "TF",
        "text": "누군가에게 피드백을 줄 때 기분을 맞추기보다 정확하고 구체적인 개선점을 먼저 말하는 편이다.",
        "explanation": "정확한 기준과 개선점을 직접 말하는 경향(T)인지, 상대가 받아들일 방식과 관계에 미치는 영향을 먼저 고려하는 경향(F)인지 살펴봅니다.",
    },
    {
        "axis": "JP",
        "text": "여행이나 주말 일정은 현장에서 정하기보다 큰 틀과 순서를 미리 정해 두는 편이다.",
        "explanation": "일정과 순서를 계획하는 경향(J)인지, 현장에서 선택할 수 있도록 여지를 두는 경향(P)인지 살펴봅니다.",
    },
]

AXES = {
    "EI": ("E", "I", "에너지를 얻고 교류하는 방식"),
    "SN": ("S", "N", "정보를 받아들이는 방식"),
    "TF": ("T", "F", "판단과 의사결정 방식"),
    "JP": ("J", "P", "일상을 계획하고 진행하는 방식"),
}

LETTER_MEANINGS = {
    "E": "외향(E): 사람들과 교류하고 바깥 활동에 참여하며 에너지를 얻는 경향",
    "I": "내향(I): 혼자 또는 소수와 생각을 정리하는 시간에서 에너지를 얻는 경향",
    "S": "감각(S): 구체적인 사실, 현재의 경험, 실제적인 정보를 중시하는 경향",
    "N": "직관(N): 패턴, 의미, 새로운 가능성과 큰 그림을 중시하는 경향",
    "T": "사고(T): 논리, 원칙, 일관된 기준을 중심으로 판단하는 경향",
    "F": "감정(F): 사람들의 가치, 관계, 결정이 미치는 영향을 중심으로 판단하는 경향",
    "J": "판단(J): 계획과 구조를 세우고 일을 정리해 마무리하는 것을 선호하는 경향",
    "P": "인식(P): 선택지를 열어 두고 상황에 맞춰 유연하게 조정하는 것을 선호하는 경향",
}


def read_answer(number: int) -> Optional[int]:
    """1~4 응답을 입력받습니다. q를 입력하면 검사를 종료합니다."""
    while True:
        raw = input(f"\n문항 {number:02d} 응답 (1~4, 종료하려면 q): ").strip().lower()
        if raw in {"q", "quit", "종료"}:
            return None
        try:
            answer = int(raw)
        except ValueError:
            print("숫자 1, 2, 3, 4 중 하나를 입력해 주세요.")
            continue
        if answer in OPTIONS:
            return answer
        print("응답 범위를 벗어났어요. 1~4 중 하나를 입력해 주세요.")


def show_explanations(answers: List[int]) -> None:
    print("\n" + "=" * 58)
    print("문항별 해설")
    print("=" * 58)
    for number, (question, answer) in enumerate(zip(QUESTIONS, answers), start=1):
        first, second, _ = AXES[question["axis"]]
        leaning = first if answer >= 3 else second
        print(f"\n{number:02d}. {question['text']}")
        print(f"    내 응답: {answer} - {OPTIONS[answer]} ({leaning} 쪽 응답)")
        print(f"    해설: {question['explanation']}")


def show_result(answers: List[int]) -> str:
    scores = {letter: 0 for pair in AXES.values() for letter in pair[:2]}
    axis_answers = {axis: [] for axis in AXES}

    for question, answer in zip(QUESTIONS, answers):
        axis = question["axis"]
        first, second, _ = AXES[axis]
        # 1~4점 응답은 첫 번째 선호에 그대로, 반대 선호에는 5-응답으로 반영합니다.
        scores[first] += answer
        scores[second] += 5 - answer
        axis_answers[axis].append(answer)

    result = []
    print("\n" + "=" * 58)
    print("축별 결과")
    print("=" * 58)
    for axis, (first, second, label) in AXES.items():
        first_score = scores[first]
        second_score = scores[second]
        chosen = first if first_score > second_score else second
        result.append(chosen)
        print(f"\n{label} ({first}–{second}): {first} {first_score}점 / {second} {second_score}점 → {chosen}")
        print(f"  {LETTER_MEANINGS[chosen]}")

    mbti = "".join(result)
    print("\n" + "=" * 58)
    print(f"검사 결과: {mbti}")
    print("=" * 58)
    print("각 글자는 E/I, S/N, T/F, J/P 축에서 상대적으로 높은 점수를 받은 쪽입니다.")
    print("이 검사는 12문항으로 만든 간이 자기점검 도구이며, 공식 MBTI 검사나 심리 진단이 아닙니다.")
    print("점수 차이가 작다면 두 성향이 비슷할 수 있고, 상황과 컨디션에 따라 답이 달라질 수 있습니다.")
    return mbti


def main() -> None:
    print("=" * 58)
    print("12문항 간이 MBTI 성향 검사")
    print("=" * 58)
    print("정답은 없습니다. 특정 상황보다 평소의 나를 떠올려 답해 주세요.")
    print("문항마다 1~4 중 하나를 입력합니다. 해설은 응답을 마친 뒤 확인할 수 있어요.")
    for number, description in OPTIONS.items():
        print(f"  {number}: {description}")
    print("※ 가운데 중립 선택지는 없습니다. 가장 가까운 쪽을 골라 주세요.")

    answers: List[int] = []
    for number, question in enumerate(QUESTIONS, start=1):
        print(f"\n[{number:02d}/12] {question['text']}")
        answer = read_answer(number)
        if answer is None:
            print("검사를 종료했습니다. 입력한 답변은 결과로 계산하지 않았습니다.")
            return
        answers.append(answer)

    show_result(answers)
    show_explanations(answers)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\n입력이 중단되어 검사를 종료합니다.")
