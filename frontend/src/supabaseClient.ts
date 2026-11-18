import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const isSupabaseConfigured = Boolean(
  supabaseUrl &&
  supabaseAnonKey &&
  supabaseUrl.startsWith('https://') &&
  !supabaseUrl.includes('your-project')
);

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  avatar_url?: string;
  isDemo?: boolean;
}

// Key for local storage persistence
const AUTH_STORAGE_KEY = 'consumer_assist_auth_user';

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: AuthUser | null) {
  if (user) {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  }
}

export async function signInWithGoogleSupabase(): Promise<void> {
  if (supabase) {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin,
      },
    });
    if (error) throw error;
  } else {
    throw new Error('Supabase is not configured yet with valid URL/keys');
  }
}

// Kept in sync from auth events. Calling supabase.auth.getSession() per request
// contends for the auth lock held during onAuthStateChange and can deadlock the page.
let currentToken: string | null = null;

export function setAccessToken(token: string | null) {
  currentToken = token;
}

export async function getAccessToken(): Promise<string | null> {
  return currentToken;
}

export async function signOutUser(): Promise<void> {
  if (supabase) {
    await supabase.auth.signOut();
  }
  setStoredUser(null);
}

