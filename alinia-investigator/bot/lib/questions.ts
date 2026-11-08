export type StoredQuestion = {
  question_id: string;
  text: string;
  status: "pending" | "answered";
  answer: string | null;
  kind: "relato" | null;
};

export function openQuestion(questionId: string, text: string): StoredQuestion {
  return { question_id: questionId, text, status: "pending", answer: null, kind: null };
}

export function rememberQuestion(questions: StoredQuestion[], question: StoredQuestion): StoredQuestion[] {
  if (questions.some((item) => item.question_id === question.question_id)) return questions;
  return [...questions, question];
}

export function answerQuestion(
  questions: StoredQuestion[],
  questionId: string,
  answer: string,
): { questions: StoredQuestion[]; found: boolean } {
  let found = false;
  const next = questions.map((item) => {
    if (item.question_id !== questionId) return item;
    found = true;
    return { ...item, status: "answered" as const, answer, kind: "relato" as const };
  });
  return { questions: next, found };
}
