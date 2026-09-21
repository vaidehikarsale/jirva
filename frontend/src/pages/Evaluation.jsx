import ComingSoonPage from "../components/ComingSoonPage";
import { BarChartIcon } from "../icons";

export default function Evaluation() {
  return (
    <ComingSoonPage
      icon={BarChartIcon}
      title="Evaluation"
      description="Retrieval precision, faithfulness, resolution accuracy, and escalation precision/recall will appear here once evaluation runs are available."
    />
  );
}
