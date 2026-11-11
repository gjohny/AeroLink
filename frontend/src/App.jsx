
import { useEffect, useRef, useState } from "react";

import Home from "./pages/Home";
import Register from "./pages/Register";
import Login from "./pages/Login";
import Preferences from "./pages/Preferences";
import AccountSettings from "./pages/AccountSettings";
import MyTrips from "./pages/MyTrips";
import Weather from "./pages/Weather";

import { getCurrentUser, logoutUser } from "./authApi";

// Temporary page for features that are still being developed.
function ComingSoon({ title, description }) {
  return (
    <section className="aero-coming-soon">
      <div className="aero-coming-soon-card">
        <span
          className="aero-coming-soon-icon"
          aria-hidden="true"
        >
          ✈
        </span>

        <h1>{title}</h1>
        <p>{description}</p>

        <span className="aero-coming-soon-label">
          Coming Soon
        </span>
      </div>
    </section>
  );
}

// Pages that will be connected to teammates' features later.
const upcomingPages = {
  "/recommendations": {
    title: "Personalized Recommendations",
    description:
      "Discover lodging, activities, and restaurants tailored to your preferences.",
  },
  "/budget": {
    title: "Budget Tracking",
    description:
      "Track travel expenses and manage your trip budget in one place.",
  },
  "/updates": {
    title: "Travel Updates",
    description:
      "Stay informed with flight alerts and weather updates for your trip.",
  },
};

const protectedPaths = [
  "/preferences",
  "/account",
  ...Object.keys(upcomingPages),
];

export default function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);

  useEffect(() => {
    if (!profileOpen) return;

    function handleOutsideClick(event) {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setProfileOpen(false);
      }
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        setProfileOpen(false);
        profileRef.current?.querySelector(".aero-profile-trigger")?.focus();
      }
    }

    document.addEventListener("pointerdown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("pointerdown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [profileOpen]);

  // Keep navigation synchronized with browser back/forward.
  useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  // Restore the logged-in user when the application loads.
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

  // Navigate without refreshing the entire application.
  function goTo(destination) {
    setProfileOpen(false);
    if (destination === window.location.pathname) return;

    window.history.pushState({}, "", destination);
    setPath(destination);
    window.scrollTo(0, 0);
  }

  function navigate(event, destination) {
    event.preventDefault();
    setProfileOpen(false);
    goTo(destination);
  }

  // Called after successful registration or login.
  function handleAuthSuccess(authenticatedUser) {
    setUser(authenticatedUser);
    goTo("/preferences");
  }

  // Log out and return to the homepage.
  async function handleLogout() {
    setProfileOpen(false);
    try {
      await logoutUser();
      setUser(null);
      goTo("/");
    } catch (error) {
      alert(error.message);
    }
  }

  // Displayed if a logged-in user opens Login or Register.
  function renderAlreadyLoggedIn() {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>You're already logged in</h1>
          <p>Welcome back, {user.name}!</p>

          <button
            type="button"
            onClick={() => goTo("/preferences")}
          >
            Continue to Preferences
          </button>
        </div>
      </div>
    );
  }

  // Select which page to display.
  let page;

  if (
    checkingAuth &&
    (path === "/login" ||
      path === "/register" ||
      (path.startsWith("/trips/") || protectedPaths.includes(path)))
  ) {
    page = (
      <p
        style={{
          textAlign: "center",
          padding: "50px",
        }}
      >
        Checking your session...
      </p>
    );
  } else if (path === "/") {
    page = <Home user={user} onNavigate={goTo} />;
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
  } else if (path === "/register") {
    page = user ? (
      renderAlreadyLoggedIn()
    ) : (
      <Register
        onSuccess={handleAuthSuccess}
        onNavigate={goTo}
      />
    );
  } else if (path === "/login") {
    page = user ? (
      renderAlreadyLoggedIn()
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
  } else if (path === "/account") {
    page = user ? (
      <AccountSettings user={user} onAccountDeleted={() => { setUser(null); goTo("/"); }} />
    ) : (
      <Login onSuccess={handleAuthSuccess} onNavigate={goTo} />
    );
  } else if (path === "/trips" || path.startsWith("/trips/")) {
    const segments = path.split("/").filter(Boolean);
    const tripId = segments.length >= 2 && /^\d+$/.test(segments[1]) ? segments[1] : null;
    const tool = segments.length === 3 ? segments[2] : null;
    const toolNames = { recommendations: "Recommendations", itineraries: "Itineraries", budget: "Budget", flights: "Flight Alerts", weather: "Weather", airports: "Airport Data" };
    page = user ? (tripId && tool === "weather" && segments.length === 3 ? (
      <Weather key={tripId} tripId={tripId} onNavigate={goTo} />
    ) : tripId && tool && toolNames[tool] ? (
      <section className="aero-coming-soon"><div className="aero-coming-soon-card">
        <h1>{toolNames[tool]}</h1>
        <button type="button" onClick={() => goTo(`/trips/${tripId}`)}>← Back to Trip</button>
      </div></section>
    ) : segments.length > 2 || (segments.length === 2 && !tripId) ? (
      <div style={{ padding: 40 }}>Trip page not found.</div>
    ) : <MyTrips onNavigate={goTo} selectedTripId={tripId} />) : (
      <Login onSuccess={handleAuthSuccess} onNavigate={goTo} />
    );
  } else if (Object.hasOwn(upcomingPages, path)) {
    page = user ? (
      <ComingSoon {...upcomingPages[path]} />
    ) : (
      <Login
        onSuccess={handleAuthSuccess}
        onNavigate={goTo}
      />
    );
  } else {
    page = (
      <div style={{ padding: "40px 32px" }}>
        <h1>Page not found</h1>
        <button type="button" onClick={() => goTo("/")}>
          Return Home
        </button>
      </div>
    );
  }

  // Navigation links for logged-in users.
  const navigationLinks = [
    ["/", "Home"],
    ...(user && !checkingAuth
      ? [
          ["/trips", "My Trips"],
        ]
      : []),
  ];

  return (
    <main className="app aero-app">
      <nav
        className="navigation"
        aria-label="Main navigation"
      >
        {/* AeroLink brand */}
        <a
          className="aero-brand"
          href="/"
          onClick={(event) => navigate(event, "/")}
        >
          <svg
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M21.5 2.5c-.7-.7-2-.6-3.1.1L11 8.1 4.3 6.7 2 9l6 3.2-3.8 3.9-2.5-.4-1.2 1.2 4.4 2.3 2.3 4.4 1.2-1.2-.4-2.5 3.9-3.8 3.2 6 2.3-2.3-1.4-6.7 5.5-7.4c.7-1.1.8-2.4.1-3.1Z" />
          </svg>
          AeroLink
        </a>

        {/* Main navigation links */}
        <div className="aero-nav-links">
          {navigationLinks.map(([destination, label]) => (
            <a
              key={destination}
              href={destination}
              aria-current={
                path === destination ? "page" : undefined
              }
              onClick={(event) =>
                navigate(event, destination)
              }
            >
              {label}
            </a>
          ))}
        </div>

        {/* Authentication and account controls */}
        <div className="aero-nav-actions">
          {!checkingAuth &&
            (user ? (
              <div className="aero-profile" ref={profileRef}>
                <button
                  type="button"
                  className="aero-profile-trigger"
                  aria-expanded={profileOpen}
                  aria-haspopup="true"
                  aria-controls="aero-profile-menu"
                  onClick={() => setProfileOpen((open) => !open)}
                >
                  <span className="aero-profile-avatar" aria-hidden="true">
                    {user.name?.charAt(0)?.toUpperCase() || "U"}
                  </span>
                  <span className="aero-profile-name">{user.name}</span>
                  <svg className="aero-profile-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                </button>

                {profileOpen && (
                  <div className="aero-profile-menu" id="aero-profile-menu">
                    <a
                      href="/preferences"
                      aria-current={path === "/preferences" ? "page" : undefined}
                      onClick={(event) => navigate(event, "/preferences")}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                        <path d="M4 7h16M4 17h16M8 4v6M16 14v6" />
                      </svg>
                      My Preferences
                    </a>
                    <a
                      href="/account"
                      aria-current={path === "/account" ? "page" : undefined}
                      onClick={(event) => navigate(event, "/account")}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                        <circle cx="12" cy="12" r="3" />
                        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l-1.87 1.87A1.7 1.7 0 0 0 16 18.4a1.7 1.7 0 0 0-1.2 1.56V21h-5.6v-1.04A1.7 1.7 0 0 0 8 18.4a1.7 1.7 0 0 0-1.87.34l-1.87-1.87A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.2H2v-3.6h1.04A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l1.87-1.87A1.7 1.7 0 0 0 8 5.6a1.7 1.7 0 0 0 1.2-1.56V3h5.6v1.04A1.7 1.7 0 0 0 16 5.6a1.7 1.7 0 0 0 1.87-.34l1.87 1.87A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.56 1.2H22v3.6h-1.04A1.7 1.7 0 0 0 19.4 15Z" />
                      </svg>
                      Account Settings
                    </a>
                    <div className="aero-profile-divider" />
                    <button type="button" className="aero-profile-logout" onClick={handleLogout}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                        <path d="M10 17l5-5-5-5M15 12H3M12 3h6a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3h-6" />
                      </svg>
                      Logout
                    </button>
                  </div>
                )}
              </div>
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
                  className="aero-nav-primary"
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
            ))}
        </div>
      </nav>

      {/* Page content */}
      <div className="aero-page-content">
        {page}
      </div>
    </main>
  );
}
