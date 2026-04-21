import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// This checks if we are on the production website or local computer
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";