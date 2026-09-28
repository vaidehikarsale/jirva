import { SAMPLE_QUESTION_GROUPS, SAMPLE_QUESTIONS } from "../sampleQuestions";
import { CompassIcon } from "../icons";
import "./FaqPanel.css";

function QuestionButton({ q, onSelect, disabled }) {
  return (
    <button
      type="button"
      className="faq-question-btn"
      onClick={() => onSelect(q)}
      disabled={disabled}
    >
      <span className="faq-question-title">{q.title}</span>
      <span className="faq-question-text">{q.question}</span>
    </button>
  );
}

export default function FaqPanel({ onSelect, disabled }) {
  return (
    <div className="panel faq-panel">
      <div className="faq-header">
        <CompassIcon width={16} height={16} />
        <h2>FAQ / Sample Questions</h2>
      </div>
      <p className="faq-note">
        All {SAMPLE_QUESTIONS.length} sample questions, by category - click one to pre-fill the form.
      </p>

      <div className="faq-scroll">
        {SAMPLE_QUESTION_GROUPS.map((group) => (
          <div key={group.category} className="faq-group">
            <h3>{group.category}</h3>
            <ul className="faq-list">
              {group.questions.map((q) => (
                <li key={q.title}>
                  <QuestionButton q={q} onSelect={onSelect} disabled={disabled} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
