export type ClarificationType =
  | "missing_info"
  | "ambiguous_requirement"
  | "approach_choice"
  | "risk_confirmation"
  | "suggestion";

export type WidgetInputType =
  | "text"
  | "single_choice"
  | "multi_choice"
  | "confirmation";

export interface WidgetHints {
  input_type: WidgetInputType;
  multi_line?: boolean;
  required?: boolean;
  risk_level?: "low" | "medium" | "high" | "critical";
  allow_custom?: boolean;
  confirm_phrase?: string;
}

export interface ClarificationStructured {
  _schema: string;
  question: string;
  clarification_type: ClarificationType;
  context: string | null;
  options: string[];
  widget_hints: WidgetHints;
}

export interface ClarificationContextValue {
  activeClarificationId: string | null;
  clarificationData: ClarificationStructured | null;
  isSubmitting: boolean;
  submitClarification: (answer: string) => Promise<void>;
  dismissClarification: () => void;
}
