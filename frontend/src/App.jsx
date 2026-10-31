
import { useEffect, useState } from "react";
import Register from "./pages/Register";
import Login from "./pages/Login";
import Preferences from "./pages/Preferences";
import { getCurrentUser, logoutUser } from "./authApi";


export default function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Keep navigation in sync with browser back/forward buttons.
  useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  // Check whether the user is already logged in.
  useEffect(() => {
    getCurrentUser()
      .then((data) => {
        setUser(data.user);
      })
      .catch(() => {
        setUser(null);
      })
      .finally(() => {
        setCheckingAuth(false);
      });
  }, []);

  // Navigate between pages without reloading the application.
  function goTo(destination) {
    if (destination === window.location.pathname) return;

    window.history.pushState({}, "", destination);
    setPath(destination);
  }

  function navigate(event, destination) {
    event.preventDefault();
    goTo(destination);
  }

  // Called after successful registration or login.
  function handleAuthSuccess(authenticatedUser) {
    setUser(authenticatedUser);
    goTo("/preferences");
  }

  // Log out and return to the homepage.
  async function handleLogout() {
    try {
      await logoutUser();
      setUser(null);
      goTo("/");
    } catch (error) {
      alert(error.message);
    }
  }

  // Select which page to display.
  let page;

  if (path === "/") {
    page = (
      <iframe
        className="page-frame"
        src="/home.html"
        title="Home page"
      />
    );
  } else if (path === "/health") {
    page = (
      <iframe
        className="page-frame"
        src="/health.html"
        title="Connection status"
      />
    );
  } else if (path === "/Page1") {
    page = (
      <iframe
        className="page-frame"
        src="/Page1.html"
        title="Page 1"
      />
    );
  } else if (path === "/Page2") {
    page = (
      <iframe
        className="page-frame"
        src="/Page2.html"
        title="Page 2"
      />
    );
  } else if (path === "/Page3") {
    page = (
      <iframe
        className="page-frame"
        src="/Page3.html"
        title="Page 3"
      />
    );
  } else if (checkingAuth) {
    page = <p>Checking your session...</p>;
  } else if (path === "/register") {
    page = user ? (
      <div className="auth-page">
        <div className="auth-card">
          <h1>You're already logged in</h1>
          <p>Welcome back, {user.name}!</p>
          <button onClick={() => goTo("/preferences")}>
            Continue to Preferences
          </button>
        </div>
      </div>
    ) : (
      <Register
        onSuccess={handleAuthSuccess}
        onNavigate={goTo}
      />
    );
  } else if (path === "/login") {
    page = user ? (
      <div className="auth-page">
        <div className="auth-card">
          <h1>You're already logged in</h1>
          <p>Welcome back, {user.name}!</p>
          <button onClick={() => goTo("/preferences")}>
            Continue to Preferences
          </button>
        </div>
      </div>
    ) : (
      <Login
        onSuccess={handleAuthSuccess}
        onNavigate={goTo}
      />
    );
  } else if (path === "/preferences") {
    page = user ? (
      <Preferences user={user} />
    ) : (
      <Login
        onSuccess={handleAuthSuccess}
        onNavigate={goTo}
      />
    );
  } else {
    page = <h1>Page not found</h1>;
  }

  return (
    <main className={`app${path === "/" ? " app-home" : ""}`}>
      <nav className="navigation" aria-label="Main navigation">
        {[
          ["/", "Home"],
          ["/Page1", "Page 1"],
          ["/Page2", "Page 2"],
          ["/Page3", "Page 3"],
        ].map(([destination, label]) => (
          <a
            key={destination}
            href={destination}
            aria-current={
              path === destination ? "page" : undefined
            }
            onClick={(event) => navigate(event, destination)}
          >
            {label}
          </a>
        ))}

        {!checkingAuth && (
          user ? (
            <>
              <a
                href="/preferences"
                aria-current={
                  path === "/preferences" ? "page" : undefined
                }
                onClick={(event) =>
                  navigate(event, "/preferences")
                }
              >
                Preferences
              </a>

              <button
                type="button"
                onClick={handleLogout}
              >
                Log Out
              </button>
            </>
          ) : (
            <>
              <a
                href="/login"
                aria-current={
                  path === "/login" ? "page" : undefined
                }
                onClick={(event) =>
                  navigate(event, "/login")
                }
              >
                Login
              </a>

              <a
                href="/register"
                aria-current={
                  path === "/register" ? "page" : undefined
                }
                onClick={(event) =>
                  navigate(event, "/register")
                }
              >
                Create Account
              </a>
            </>
          )
        )}
      </nav>

      {page}
    </main>
  );
}
