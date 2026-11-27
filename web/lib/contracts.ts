export const statuses = [
  ["wishlist", "Wishlist"],
  ["applied", "Applied"],
  ["phone_screen", "Phone screen"],
  ["interview", "Interview"],
  ["offer", "Offer"],
  ["accepted", "Accepted"],
  ["rejected", "Rejected"],
] as const;

export type JobStatus = (typeof statuses)[number][0];

export interface JobFields {
  company: string;
  role: string;
  status: JobStatus;
  job_url: string | null;
  deadline: string | null;
  notes: string | null;
}

export interface JobApplication extends JobFields {
  id: string;
  applied_at: string | null;
  created_at: string;
}

export interface Viewer {
  id: string;
  email: string;
  full_name: string | null;
}
