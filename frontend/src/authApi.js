
async function authRequest(endpoint, options = {}) {
  const response = await fetch(`/api/auth/${endpoint}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Something went wrong.");
  }

  return data;
}

export function registerUser(name, email, password) {
  return authRequest("register", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
}

export function loginUser(email, password) {
  return authRequest("login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getCurrentUser() {
  return authRequest("me");
}

export function logoutUser() {
  return authRequest("logout", {
    method: "POST",
  });
}
