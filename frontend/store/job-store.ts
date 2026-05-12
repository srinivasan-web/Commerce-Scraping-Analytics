import { create } from "zustand";
import type { Job } from "@/types";

interface JobState {
  liveJob?: Job;
  setLiveJob: (job?: Job) => void;
}

export const useJobStore = create<JobState>((set) => ({
  liveJob: undefined,
  setLiveJob: (job) => set({ liveJob: job })
}));

