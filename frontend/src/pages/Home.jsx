
import "../home.css";

const features = [
  {
    icon: "calendar",
    title: "Smart Itineraries",
    description: "Organize your trip effortlessly.",
  },
  {
    icon: "heart",
    title: "Personalized Recommendations",
    description: "Places that match your interests.",
  },
  {
    icon: "wallet",
    title: "Budget Planning",
    description: "Stay on track with your spending.",
  },
  {
    icon: "weather",
    title: "Travel Updates",
    description: "Get flight and weather alerts.",
  },
];

function FeatureIcon({ type }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };

  if (type === "calendar") {
    return (
      <svg viewBox="0 0 24 24" {...common}>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4M17 3v4M3 10h18" />
      </svg>
    );
  }

  if (type === "heart") {
    return (
      <svg viewBox="0 0 24 24" {...common}>
        <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />
      </svg>
    );
  }

  if (type === "wallet") {
    return (
      <svg viewBox="0 0 24 24" {...common}>
        <rect x="3" y="6" width="18" height="15" rx="2" />
        <path d="M3 9V5a2 2 0 0 1 2-2h13M15 13h6v5h-6a2.5 2.5 0 0 1 0-5Z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" {...common}>
      <path d="M5 17a4 4 0 0 1 1-7.9A7 7 0 0 1 19 11a3.5 3.5 0 0 1-1 6H5Z" />
      <path d="M8 3l-1 2M15 2v2M21 6l-2 1" />
    </svg>
  );
}

export default function Home({ user, onNavigate }) {
  function handleGetStarted() {
    onNavigate(user ? "/trips" : "/register");
  }

  return (
    <div className="aero-home">
      <section className="aero-home-hero">
        <div className="aero-home-hero-content">
          <h1>
            AeroLink
            <span>Your Personalized Travel Companion</span>
          </h1>

          <p>
            Discover the best places to stay, explore, and dine
            — tailored to your travel style.
          </p>

          <button
            type="button"
            className="aero-home-cta"
            onClick={handleGetStarted}
          >
            {user ? "Continue Planning" : "Get Started"}
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>

      <section className="aero-home-features" aria-labelledby="aero-features-title">
        <h2 id="aero-features-title">Plan Smarter, Travel Better</h2>

        <div className="aero-home-feature-grid">
          {features.map((feature) => (
            <article className="aero-home-feature" key={feature.title}>
              <div className="aero-home-feature-icon">
                <FeatureIcon type={feature.icon} />
              </div>

              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
