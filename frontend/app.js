"use strict";

// --- Configuration -----------------------------------------------------------
// Point this at the auth/list server. Default is the local mock test server.
// For the real test server from the brief, change it to "http://localhost".
const API_BASE_URL = "http://localhost:8001";

// The mock server ignores these; the real server needs real values. Kept here so
// the login form can stay simple (username + password only).
const CLIENT_ID = "";
const CLIENT_SECRET = "";

// Non-standard auth header used by this API (mirrors AUTH_HEADER_NAME on the
// backend). Switching to "Authorization" would be a one-line change here.
const AUTH_HEADER = "Access-Token";
const TOKEN_KEY = "access_token";

// Employee fields rendered into the table body, in column order.
const COLUMNS = [
  "first_name",
  "last_name",
  "email",
  "title",
  "country",
  "rating",
  "date_of_birth",
];

// --- Element references -------------------------------------------------------
const loginView = document.getElementById("login-view");
const tableView = document.getElementById("table-view");
const loginForm = document.getElementById("login-form");
const loginBtn = document.getElementById("login-btn");
const loginError = document.getElementById("login-error");
const tableError = document.getElementById("table-error");
const tableBody = document.getElementById("employees-body");
const countEl = document.getElementById("count");
const logoutBtn = document.getElementById("logout-btn");

// --- View toggling ------------------------------------------------------------
function showLogin() {
  tableView.hidden = true;
  loginView.hidden = false;
}

function showTable() {
  loginView.hidden = true;
  tableView.hidden = false;
}

function setError(el, message) {
  if (message) {
    el.textContent = message;
    el.hidden = false;
  } else {
    el.textContent = "";
    el.hidden = true;
  }
}

// --- Auth ---------------------------------------------------------------------
async function login(username, password) {
  const res = await fetch(`${API_BASE_URL}/api/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "password",
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      username,
      password,
    }),
  });

  if (!res.ok) {
    throw new Error(`Login failed (HTTP ${res.status}).`);
  }

  const data = await res.json();
  if (!data.access_token) {
    throw new Error("Login response did not include a token.");
  }
  sessionStorage.setItem(TOKEN_KEY, data.access_token);
}

function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  setError(tableError, "");
  showLogin();
}

// --- Employee list ------------------------------------------------------------
async function loadEmployees() {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) {
    showLogin();
    return;
  }

  setError(tableError, "");
  let res;
  try {
    res = await fetch(`${API_BASE_URL}/api/employee/list/`, {
      headers: { [AUTH_HEADER]: token },
    });
  } catch (err) {
    setError(tableError, `Could not reach the server at ${API_BASE_URL}.`);
    return;
  }

  if (res.status === 401) {
    // Token missing/expired/invalid — drop back to the login screen.
    logout();
    return;
  }
  if (!res.ok) {
    setError(tableError, `Failed to load employees (HTTP ${res.status}).`);
    return;
  }

  const employees = await res.json();
  renderEmployees(employees);
}

function renderEmployees(employees) {
  tableBody.replaceChildren();
  countEl.textContent = `(${employees.length})`;

  for (const emp of employees) {
    const row = document.createElement("tr");

    // Avatar cell (image URL from the API).
    const avatarCell = document.createElement("td");
    if (emp.image) {
      const img = document.createElement("img");
      img.className = "avatar";
      img.src = emp.image;
      img.alt = "";
      img.addEventListener("error", () => img.remove());
      avatarCell.appendChild(img);
    }
    row.appendChild(avatarCell);

    // Data cells. Using textContent keeps server data from being interpreted
    // as HTML (no injection from employee fields).
    for (const field of COLUMNS) {
      const cell = document.createElement("td");
      cell.textContent = emp[field] != null ? String(emp[field]) : "";
      row.appendChild(cell);
    }

    tableBody.appendChild(row);
  }
}

// --- Wiring -------------------------------------------------------------------
loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError(loginError, "");
  loginBtn.disabled = true;
  try {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    await login(username, password);
    showTable();
    await loadEmployees();
  } catch (err) {
    setError(loginError, err.message || "Login failed.");
  } finally {
    loginBtn.disabled = false;
  }
});

logoutBtn.addEventListener("click", logout);

// On load: if already authenticated (token in sessionStorage), go to the table.
if (sessionStorage.getItem(TOKEN_KEY)) {
  showTable();
  loadEmployees();
} else {
  showLogin();
}
