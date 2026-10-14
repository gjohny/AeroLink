import { useEffect, useState } from "react";

export default function App() {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    function handlePopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function navigate(event, destination) {
    event.preventDefault();
    if (destination === path) return;
    window.history.pushState({}, "", destination);
    setPath(destination);
  }

  let page;
  if (path === "/") {
    page = <iframe className="page-frame" src="/home.html" title="Home page" />;
  } else if (path === "/health") {
    page = <iframe className="page-frame" src="/health.html" title="Connection status" />;
  } else if (path === "/Page1") {
    page = <iframe className="page-frame" src="/Page1.html" title="Page 1" />;
  } else if (path === "/Page2") {
    page = <iframe className="page-frame" src="/Page2.html" title="Page 2" />;
  } else if (path === "/Page3") {
    page = <iframe className="page-frame" src="/Page3.html" title="Page 3" />;
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
            aria-current={path === destination ? "page" : undefined}
            onClick={(event) => navigate(event, destination)}
          >
            {label}
          </a>
        ))}
      </nav>
      {page}
    </main>
  );
}
