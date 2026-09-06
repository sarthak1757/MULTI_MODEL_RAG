interface Props {
  question: string;
  disabled: boolean;
  loading: boolean;
  onChange: (value: string) => void;
  onAsk: () => void;
}

export default function QuestionBox({ question, disabled, loading, onChange, onAsk }: Props) {
  return (
    <section className="panel">
      <span className="eyebrow">Question</span>
      <textarea value={question} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      <button className="primaryButton" disabled={disabled || loading || !question.trim()} onClick={onAsk}>
        {loading ? "Asking..." : "Ask"}
      </button>
    </section>
  );
}
