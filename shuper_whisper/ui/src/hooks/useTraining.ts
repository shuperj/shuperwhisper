import { useState, useEffect, useCallback } from "react";
import type { TrainingStatus } from "@/lib/types";

/**
 * Receives real-time training status updates from Python via
 * window.__onTrainingStatus(), which Python calls through evaluate_js().
 */
export function useTraining() {
  const [trainingStatus, setTrainingStatus] =
    useState<TrainingStatus | null>(null);

  useEffect(() => {
    window.__onTrainingStatus = (data: unknown) => {
      setTrainingStatus(data as TrainingStatus);
    };
    return () => {
      delete window.__onTrainingStatus;
    };
  }, []);

  const clearTraining = useCallback(() => {
    setTrainingStatus(null);
  }, []);

  return { trainingStatus, clearTraining };
}
