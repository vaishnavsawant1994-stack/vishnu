const BEARER_KEY = "grok-auth.bearer-token";

export function rememberSession(token: string) {
  sessionStorage.setItem(BEARER_KEY, token);
}
