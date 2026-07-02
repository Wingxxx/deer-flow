"use client";
import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
} from "react";
import type { ClarificationContextValue, ClarificationStructured } from "./types";

const ClarificationContext = createContext<ClarificationContextValue>({
  activeClarificationId: null,
  clarificationData: null,
  isSubmitting: false,
  submitClarification: async () => {},
  dismissClarification: () => {},
});

export function ClarificationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [activeClarificationId, setActiveClarificationId] =
    useState<string | null>(null);
  const [clarificationData, setClarificationData] =
    useState<ClarificationStructured | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inFlightRef = useRef(false);

  const submitClarification = useCallback(
    async (answer: string) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setIsSubmitting(true);
      try {
        window.dispatchEvent(
          new CustomEvent("clarification:submit", {
            detail: { answer, clarificationId: activeClarificationId },
          }),
        );
        setActiveClarificationId(null);
        setClarificationData(null);
      } finally {
        setIsSubmitting(false);
        inFlightRef.current = false;
      }
    },
    [activeClarificationId],
  );

  const dismissClarification = useCallback(() => {
    setActiveClarificationId(null);
    setClarificationData(null);
  }, []);

  return (
    <ClarificationContext.Provider
      value={{
        activeClarificationId,
        clarificationData,
        isSubmitting,
        submitClarification,
        dismissClarification,
      }}
    >
      {children}
    </ClarificationContext.Provider>
  );
}

export function useClarification() {
  return useContext(ClarificationContext);
}
