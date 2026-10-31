import {
  ArrowRight,
  ArrowUpRight,
  Atom,
  BadgeCheck,
  Box,
  Bot,
  Check,
  ChevronRight,
  Factory,
  FileCog,
  Gauge,
  Layers,
  Menu,
  MessageSquareText,
  Rocket,
  Ruler,
  ScanLine,
  ShieldCheck,
  Shirt,
  Sparkles,
  Wand2,
  Workflow,
  Wrench,
  X,
} from "lucide-react";
import { type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { Brand } from "./Brand";
import { LinkageScene } from "./LinkageScene";
import { Reveal } from "./Reveal";
import "./landing.css";

const EARLY_ACCESS = "mailto:hello@mechanism.ai?subject=Mechanism%20AI%20early%20access";
const CONTACT = "mailto:hello@mechanism.ai";

const NAV_LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "Capabilities", href: "#capabilities" },
  { label: "Industries", href: "#industries" },
  { label: "Roadmap", href: "#roadmap" },
  { label: "About", href: "#about" },
];

const STEPS = [
  {
    index: "01",
    icon: MessageSquareText,
    title: "Describe Your Idea",
    body: "Enter natural-language instructions or upload a reference sketch. Mechanism AI captures constraints, dimensions and intent.",
    meta: "Natural language · sketch input",
  },
  {
    index: "02",
    icon: Wand2,
    title: "Generate Your Design",
    body: "AI interprets engineering intent and produces structured specifications and editable geometry.",
    meta: "Structured spec · parametric geometry",
  },
  {
    index: "03",
    icon: Atom,
    title: "Simulate the Physics",
    body: "Run simulations to understand movement, forces and physical behavior before committing to hardware.",
    meta: "Kinematics · motion traces",
  },
  {
    index: "04",
    icon: BadgeCheck,
    title: "Validate and Export",
    body: "Check design constraints with deterministic evaluation and prepare engineering deliverables.",
    meta: "Constraints · CAD exports",
  },
];

const CAPABILITIES = [
  {
    icon: Sparkles,
    title: "AI-Powered Design",
    body: "Transform natural-language instructions into structured engineering specifications, assumptions and clarification questions.",
    tag: "Intent → specification",
    wide: true,
  },
  {
    icon: Box,
    title: "3D CAD Generation",
    body: "Generate editable geometry and mechanical assemblies with parameterized parts, joints and envelopes.",
    tag: "Parametric CAD",
    wide: true,
  },
  {
    icon: Gauge,
    title: "Physics Simulation",
    body: "Explore real mechanical behavior through kinematic simulation and motion traces.",
    tag: "Motion analysis",
    wide: false,
  },
  {
    icon: ShieldCheck,
    title: "Engineering Validation",
    body: "Evaluate dimensions, constraints and simulated behavior with deterministic checks and evidence bundles.",
    tag: "Independent checks",
    wide: false,
  },
  {
    icon: FileCog,
    title: "Engineering Exports",
    body: "Prepare engineering documentation, simulation evidence and supported design files.",
    tag: "Deliverables",
    wide: false,
  },
];

const SHOWCASE_POINTS = [
  {
    icon: Ruler,
    title: "Engineering dimensions",
    body: "Link lengths, envelopes and pivot diameters stay explicit and editable.",
  },
  {
    icon: ScanLine,
    title: "Joint positions",
    body: "Every revolute and prismatic joint is declared with an axis and motion range.",
  },
  {
    icon: Workflow,
    title: "Simulation trajectory",
    body: "Motion is computed from physics, sampled and persisted with the design.",
  },
  {
    icon: Layers,
    title: "Editable artifacts",
    body: "CAD geometry, specifications and evidence are generated as real engineering outputs.",
  },
];

const INDUSTRIES = [
  {
    icon: Wrench,
    name: "Mechanical Engineering",
    body: "Design mechanical systems, mechanisms and assemblies with simulation-backed validation.",
    status: "available",
    statusLabel: "Initial product focus",
    note: "Available now",
  },
  {
    icon: Shirt,
    name: "Fashion Engineering",
    body: "Create 2D garment patterns, 3D garments and manufacturing specifications.",
    status: "planned",
    statusLabel: "Planned",
    note: "Coming soon",
  },
  {
    icon: Bot,
    name: "Robotics Design",
    body: "Design, simulate and validate robotic assemblies and mechanisms.",
    status: "planned",
    statusLabel: "Planned",
    note: "Coming soon",
  },
];

const ROADMAP: {
  phase: string;
  title: string;
  body: string;
  status: IndustryStatus;
}[] = [
  {
    phase: "Phase 1",
    title: "AI-assisted mechanical design and simulation",
    body: "Four-bar linkage design, deterministic physics simulation and geometry generation.",
    status: "available",
  },
  {
    phase: "Phase 2",
    title: "Advanced CAD generation and engineering validation",
    body: "Model-authored CAD programs for parts, assemblies and structural frames; broader validation.",
    status: "development",
  },
  {
    phase: "Phase 3",
    title: "Robotics design and simulation",
    body: "Robotic assemblies, jointed mechanisms and motion validation at platform scale.",
    status: "planned",
  },
  {
    phase: "Phase 4",
    title: "Fashion engineering and garment simulation",
    body: "2D patterns, 3D garments and manufacturing-ready specifications.",
    status: "planned",
  },
  {
    phase: "Phase 5",
    title: "A unified physical product design platform",
    body: "One connected environment across engineering verticals.",
    status: "planned",
  },
];

type IndustryStatus = "available" | "planned" | "development";

function statusLabel(status: IndustryStatus): string {
  if (status === "available") {
    return "Available now";
  }
  if (status === "development") {
    return "In development";
  }
  return "Planned";
}

function SectionHeading({
  eyebrow,
  title,
  lede,
  align = "center",
}: {
  eyebrow: string;
  title: string;
  lede?: string;
  align?: "center" | "left";
}) {
  return (
    <div className={`section-heading section-heading-${align}`}>
      <span className="eyebrow-chip">{eyebrow}</span>
      <h2>{title}</h2>
      {lede ? <p className="section-lede">{lede}</p> : null}
    </div>
  );
}

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className="nav-link" href={href}>
      {children}
    </a>
  );
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">
      <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.42c.58.11.79-.25.79-.56v-2c-3.2.7-3.88-1.36-3.88-1.36-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.78 1.19 1.78 1.19 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.73-1.56-2.55-.29-5.23-1.28-5.23-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.19a11 11 0 0 1 5.79 0c2.2-1.5 3.17-1.19 3.17-1.19.63 1.59.23 2.76.12 3.05.74.81 1.19 1.84 1.19 3.1 0 4.43-2.69 5.4-5.25 5.69.41.35.78 1.05.78 2.12v3.14c0 .31.21.68.8.56A11.5 11.5 0 0 0 12 .5z" />
    </svg>
  );
}

function LinkedinIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">
      <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05 4.03 0 4.78 2.65 4.78 6.1V21h-4v-5.5c0-1.31-.02-3-1.83-3-1.83 0-2.11 1.43-2.11 2.9V21H9z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
      <path d="M18.9 2H22l-6.8 7.8L23.3 22h-6.3l-4.9-6.4L6.5 22H3.4l7.3-8.3L1 2h6.4l4.4 5.8L18.9 2zm-1.1 18h1.7L7.3 3.9H5.5L17.8 20z" />
    </svg>
  );
}

const IconTile = ({ icon: Icon }: { icon: LucideIcon }) => (
  <span className="icon-tile">
    <Icon size={20} strokeWidth={1.7} />
  </span>
);

export function LandingPage() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.body.classList.add("landing-body");
    return () => document.body.classList.remove("landing-body");
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  return (
    <div className="landing">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className={`nav${scrolled || menuOpen ? " nav-scrolled" : ""}`}>
        <div className="nav-inner">
          <a className="nav-brand" href="#top" aria-label="Mechanism AI home">
            <Brand />
          </a>

          <nav className="nav-links" aria-label="Primary">
            {NAV_LINKS.map((link) => (
              <NavLink key={link.href} href={link.href}>
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="nav-actions">
            <a className="nav-signin" href="#/app">
              Demo
            </a>
            <a className="btn btn-primary btn-sm" href={EARLY_ACCESS}>
              Get Early Access
            </a>
            <button
              type="button"
              className="nav-burger"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              onClick={() => setMenuOpen((value) => !value)}
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {menuOpen ? (
          <div className="nav-mobile" id="mobile-nav">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href} onClick={() => setMenuOpen(false)}>
                {link.label}
                <ChevronRight size={16} />
              </a>
            ))}
            <a href="#/app" onClick={() => setMenuOpen(false)}>
              Demo
              <ChevronRight size={16} />
            </a>
            <a className="btn btn-primary" href={EARLY_ACCESS} onClick={() => setMenuOpen(false)}>
              Get Early Access
            </a>
          </div>
        ) : null}
      </header>

      <main id="main">
        <section className="hero" id="top">
          <div className="hero-backdrop" aria-hidden="true" />
          <div className="hero-inner">
            <div className="hero-copy">
              <Reveal>
                <span className="pill">
                  <span className="pill-dot" />
                  AI-native physical design
                </span>
              </Reveal>
              <Reveal delay={0.06}>
                <h1>
                  From idea to <span className="text-gradient">engineered reality.</span>
                </h1>
              </Reveal>
              <Reveal delay={0.12}>
                <p className="hero-lede">
                  Design, simulate and validate physical products with AI. Transform
                  engineering instructions into editable 3D models and physically verified
                  designs.
                </p>
              </Reveal>
              <Reveal delay={0.18}>
                <div className="hero-actions">
                  <a className="btn btn-primary" href="#/app">
                    Start Designing
                    <ArrowRight size={17} />
                  </a>
                  <a className="btn btn-ghost" href="#platform">
                    Explore the Platform
                  </a>
                </div>
              </Reveal>
              <Reveal delay={0.24}>
                <ul className="hero-proof">
                  <li>
                    <Ruler size={15} /> Dimensions &amp; constraints
                  </li>
                  <li>
                    <Atom size={15} /> Physics simulation
                  </li>
                  <li>
                    <BadgeCheck size={15} /> Independent validation
                  </li>
                </ul>
              </Reveal>
            </div>

            <Reveal delay={0.14} className="hero-visual">
              <div className="hero-visual-glow" aria-hidden="true" />
              <LinkageScene className="hero-canvas" />
              <span className="scene-tag scene-tag-a">GROUND · 120 mm</span>
              <span className="scene-tag scene-tag-b">PIVOT · Ø 8 mm</span>
              <span className="scene-tag scene-tag-c">θ 42.0°</span>
              <span className="scene-tag scene-tag-d">
                <span className="status-dot status-dot-live" />
                KINEMATICS VALIDATED
              </span>
              <svg className="scene-dimension" viewBox="0 0 320 24" aria-hidden="true">
                <line x1="8" y1="12" x2="312" y2="12" />
                <line x1="8" y1="4" x2="8" y2="20" />
                <line x1="312" y1="4" x2="312" y2="20" />
              </svg>
            </Reveal>
          </div>

          <Reveal delay={0.2} className="hero-strip">
            <div className="hero-strip-item">
              <span className="strip-label">Engineering artifacts</span>
              Editable CAD geometry, not generated imagery
            </div>
            <div className="hero-strip-item">
              <span className="strip-label">Evaluation engine</span>
              Deterministic checks with persisted evidence
            </div>
            <div className="hero-strip-item">
              <span className="strip-label">Current focus</span>
              Mechanical engineering · Initial product
            </div>
          </Reveal>
        </section>

        <section className="section" id="how">
          <Reveal>
            <SectionHeading
              eyebrow="How it works"
              title="Engineering, reimagined."
              lede="From a simple idea to a physically validated design in one connected workflow."
            />
          </Reveal>
          <div className="steps">
            {STEPS.map((step, index) => (
              <Reveal key={step.index} delay={index * 0.06} className="step-item">
                <article className="step-card">
                  <div className="step-top">
                    <span className="step-index">{step.index}</span>
                    <span className="step-icon">
                      <step.icon size={20} strokeWidth={1.7} />
                    </span>
                  </div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                  <span className="step-meta">{step.meta}</span>
                </article>
              </Reveal>
            ))}
          </div>
        </section>

        <section className="section" id="capabilities">
          <Reveal>
            <SectionHeading
              eyebrow="Platform capabilities"
              title="Everything you need to engineer physical products."
              lede="A connected pipeline from design intent to validated, exportable engineering artifacts."
            />
          </Reveal>
          <div className="capability-grid" id="platform">
            {CAPABILITIES.map((capability, index) => (
              <Reveal
                key={capability.title}
                delay={index * 0.05}
                className={`cap-item${capability.wide ? " cap-item-wide" : ""}`}
              >
                <article className="cap-card">
                  <div className="cap-head">
                    <IconTile icon={capability.icon} />
                    <span className="cap-tag">{capability.tag}</span>
                  </div>
                  <h3>{capability.title}</h3>
                  <p>{capability.body}</p>
                  <span className="cap-line" aria-hidden="true" />
                </article>
              </Reveal>
            ))}
          </div>
          <p className="fine-print">
            Capabilities describe the platform workflow. Mechanical engineering is available
            today; simulation covers kinematics and geometry, not certified structural analysis.
          </p>
        </section>

        <section className="section" id="showcase">
          <Reveal>
            <SectionHeading
              align="left"
              eyebrow="Product showcase"
              title="See your ideas come to life."
              lede="Mechanism AI generates real engineering artifacts — editable geometry, declared joints and simulation evidence."
            />
          </Reveal>

          <div className="showcase-grid">
            <Reveal className="showcase-copy">
              <ul className="showcase-points">
                {SHOWCASE_POINTS.map((point) => (
                  <li key={point.title}>
                    <IconTile icon={point.icon} />
                    <div>
                      <h3>{point.title}</h3>
                      <p>{point.body}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <a className="btn btn-primary" href="#/app">
                Explore the Platform
                <ArrowUpRight size={17} />
              </a>
              <span className="showcase-note">
                Live four-bar linkage run · dimensions, joints and motion verified by the
                evaluation engine
              </span>
            </Reveal>

            <Reveal delay={0.1} className="showcase-visual">
              <figure className="app-mockup" aria-label="Mechanism AI workspace preview">
                <div className="mockup-bar">
                  <span className="mockup-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="mockup-title">Mechanism AI · Run 042</span>
                  <span className="mockup-badge">
                    <Check size={12} /> VALIDATED
                  </span>
                </div>
                <div className="mockup-grid">
                  <aside className="mockup-panel">
                    <span className="mockup-label">PARAMETERS</span>
                    <dl>
                      <div>
                        <dt>Ground</dt>
                        <dd>120 mm</dd>
                      </div>
                      <div>
                        <dt>Crank</dt>
                        <dd>40 mm</dd>
                      </div>
                      <div>
                        <dt>Coupler</dt>
                        <dd>100 mm</dd>
                      </div>
                      <div>
                        <dt>Rocker</dt>
                        <dd>90 mm</dd>
                      </div>
                      <div>
                        <dt>Pivot</dt>
                        <dd>Ø 8 mm</dd>
                      </div>
                    </dl>
                    <span className="mockup-label">JOINTS</span>
                    <ul className="mockup-joints">
                      <li>
                        <span>J1 · revolute</span>
                        <code>Z</code>
                      </li>
                      <li>
                        <span>J2 · revolute</span>
                        <code>Z</code>
                      </li>
                      <li>
                        <span>J3 · revolute</span>
                        <code>Z</code>
                      </li>
                    </ul>
                  </aside>
                  <div className="mockup-stage">
                    <LinkageScene variant="showcase" className="mockup-scene" />
                    <span className="stage-tag">θ 42.0°</span>
                    <span className="stage-tag stage-tag-alt">ROCKER · 90 mm</span>
                    <svg className="trajectory" viewBox="0 0 220 90" aria-hidden="true">
                      <path
                        className="trajectory-path"
                        d="M12 66 C 46 22, 92 16, 122 34 S 178 78, 210 48"
                      />
                      <circle cx="12" cy="66" r="3" />
                      <circle cx="122" cy="34" r="3" />
                      <circle cx="210" cy="48" r="3" />
                    </svg>
                  </div>
                </div>
                <div className="mockup-foot">
                  <div className="mockup-checks">
                    <span>
                      <Check size={12} /> travel 96.2 mm
                    </span>
                    <span>
                      <Check size={12} /> footprint 130 mm
                    </span>
                    <span>
                      <Check size={12} /> cycle complete
                    </span>
                  </div>
                  <span className="export-chip">
                    <FileCog size={13} /> Export STL
                  </span>
                </div>
              </figure>
              <span className="mockup-caption">
                Illustrative interface · sample four-bar linkage
              </span>
            </Reveal>
          </div>
        </section>

        <section className="section" id="industries">
          <Reveal>
            <SectionHeading
              eyebrow="Industries"
              title="One platform. Multiple physical design industries."
              lede="Mechanical engineering is the initial product focus. Planned verticals are not available today."
            />
          </Reveal>
          <div className="industry-grid">
            {INDUSTRIES.map((industry, index) => (
              <Reveal key={industry.name} delay={index * 0.06} className="industry-item">
                <article className={`industry-card industry-${industry.status}`}>
                  <div className="industry-head">
                    <IconTile icon={industry.icon} />
                    <span className={`status-pill status-${industry.status}`}>
                      {industry.statusLabel}
                    </span>
                  </div>
                  <h3>{industry.name}</h3>
                  <p>{industry.body}</p>
                  <span className="industry-note">{industry.note}</span>
                </article>
              </Reveal>
            ))}
          </div>
          <Reveal className="industry-future">
            <span className="industry-future-icon">
              <Factory size={18} strokeWidth={1.7} />
            </span>
            <div>
              <h3>Industrial Product Design</h3>
              <p>Future expansion across physical product categories.</p>
            </div>
            <span className="status-pill status-planned">Exploratory</span>
          </Reveal>
        </section>

        <section className="section" id="roadmap">
          <Reveal>
            <SectionHeading
              eyebrow="Roadmap"
              title="Building the future of physical design."
              lede="A deliberate path from focused mechanical design to a unified physical product platform."
            />
          </Reveal>
          <div className="timeline">
            {ROADMAP.map((item, index) => (
              <Reveal key={item.phase} delay={index * 0.05} className="timeline-item">
                <article className={`timeline-card timeline-${item.status}`}>
                  <div className="timeline-head">
                    <span className="timeline-phase">{item.phase}</span>
                    <span className={`status-pill status-${item.status}`}>
                      {statusLabel(item.status)}
                    </span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <span className="timeline-node" aria-hidden="true" />
                </article>
              </Reveal>
            ))}
          </div>
          <p className="fine-print">
            Roadmap is directional. Planned and in-development phases are not available today.
          </p>
        </section>

        <section className="cta-section" id="early-access">
          <Reveal className="cta-panel">
            <div className="cta-glow" aria-hidden="true" />
            <span className="pill pill-light">
              <Rocket size={13} /> Early access
            </span>
            <h2>Your next engineering breakthrough starts with an idea.</h2>
            <p>
              Join the next generation of engineers designing physical products with AI.
            </p>
            <div className="cta-actions">
              <a className="btn btn-light" href={EARLY_ACCESS}>
                Get Early Access
                <ArrowRight size={17} />
              </a>
              <a className="btn btn-outline-light" href="#platform">
                Explore Mechanism AI
              </a>
            </div>
            <span className="cta-note">
              Early access is rolling out to mechanical engineering teams first.
            </span>
          </Reveal>
        </section>
      </main>

      <footer className="footer" id="about">
        <div className="footer-inner">
          <div className="footer-brand">
            <Brand />
            <p>
              Mechanism AI transforms natural-language instructions, sketches and ideas into
              editable engineering designs, physically simulated models and validated product
              specifications.
            </p>
            <p className="footer-tagline">From idea to engineered reality.</p>
          </div>
          <div className="footer-cols">
            <div>
              <h3>Platform</h3>
              <a href="#platform">Capabilities</a>
              <a href="#how">How it works</a>
              <a href="#showcase">Product</a>
              <a href="#/app">Demo</a>
            </div>
            <div>
              <h3>Industries</h3>
              <a href="#industries">Mechanical Engineering</a>
              <a href="#industries">Fashion Engineering</a>
              <a href="#industries">Robotics Design</a>
            </div>
            <div>
              <h3>Company</h3>
              <a href="#about">About</a>
              <a href={CONTACT}>Contact</a>
              <a href="#privacy">Privacy Policy</a>
              <a href="#terms">Terms of Service</a>
            </div>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Mechanism AI. All rights reserved.</span>
          <div className="socials">
            <a href="#top" aria-label="Mechanism AI on GitHub">
              <GithubIcon />
            </a>
            <a href="#top" aria-label="Mechanism AI on LinkedIn">
              <LinkedinIcon />
            </a>
            <a href="#top" aria-label="Mechanism AI on X">
              <XIcon />
            </a>
          </div>
          <span>Conceptual geometry · Not certified engineering</span>
        </div>
      </footer>
    </div>
  );
}
