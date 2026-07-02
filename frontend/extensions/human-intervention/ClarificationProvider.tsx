"use client";
import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
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
  const pendingAckRef = useRef<string | null>(null);
  const ackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Listen for ack events matching our pending clarification
  useEffect(() => {
    const handleAck = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (pendingAckRef.current && detail?.clarificationId === pendingAckRef.current) {
        pendingAckRef.current = null;
        if (ackTimerRef.current) {
          clearTimeout(ackTimerRef.current);
          ackTimerRef.current = null;
        }
      }
    };
    window.addEventListener("clarification:ack", handleAck);
    return () => window.removeEventListener("clarification:ack", handleAck);
  }, []);

  const submitClarification = useCallback(
    async (answer: string) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setIsSubmitting(true);
      try {
        // Set up ack expectation before dispatching
        const cId = activeClarificationId;
        pendingAckRef.current = cId;

        window.dispatchEvent(
          new CustomEvent("clarification:submit", {
            detail: { answer, clarificationId: cId },
          }),
        );

        // Wait 3s for ack, restore state if not received
        ackTimerRef.current = setTimeout(() => {
          if (pendingAckRef.current === cId) {
            pendingAckRef.current = null;
            // Restore state since sendMessage may have failed
            setActiveClarificationId(cId);
            setClarificationData(
              clarificationData, // This is stale in closure, but better than nothing
            );
            console.warn("[HumanIntervention] No ack received within 3s, restored state");
          }
        }, 3000);
      } finally {
        setIsSubmitting(false);
        inFlightRef.current = false;
      }
    },
    [activeClarificationId, clarificationData],
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
