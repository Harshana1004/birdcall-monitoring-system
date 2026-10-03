import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Link,
  NavLink,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { initials } from "../../utils/format";
import Logo from "../Logo";


const LINKS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/devices", label: "Devices" },
  { to: "/detections", label: "Detections" },
  { to: "/analysis", label: "Manual analysis" },
];


function NavBar() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuRef = useRef(null);

  const links = isAdmin
    ? [...LINKS, { to: "/admin", label: "Admin" }]
    : LINKS;


  // Close menus when navigating or clicking elsewhere.
  useEffect(() => {
    setMenuOpen(false);
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function handleClick(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClick);

    return () => document.removeEventListener("mousedown", handleClick);
  }, []);


  function handleLogout() {
    logout();
    navigate("/login");
  }


  const navLinkClass = ({ isActive }) =>
    isActive ? "nav-link active" : "nav-link";


  return (
    <header className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand">
          <Logo />
          <span>
            Avian<span className="brand-accent">Acoustics</span>
          </span>
        </Link>

        <nav className="nav-links">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={navLinkClass}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="nav-user" ref={menuRef}>
          <button
            type="button"
            className="avatar-button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <span className="avatar">{initials(user)}</span>
            <span className="avatar-name">
              {user?.display_name || user?.email}
            </span>
          </button>

          {menuOpen && (
            <div className="dropdown" role="menu">
              <div className="dropdown-header">
                <div className="small">{user?.display_name || "Signed in"}</div>
                <div className="small faint">{user?.email}</div>
                {isAdmin && (
                  <span className="badge badge-green" style={{ marginTop: 6 }}>
                    Admin
                  </span>
                )}
              </div>

              <Link to="/account" className="dropdown-item" role="menuitem">
                Account settings
              </Link>
              <Link to="/analysis/history" className="dropdown-item" role="menuitem">
                My analyses
              </Link>
              <button
                type="button"
                className="dropdown-item"
                role="menuitem"
                onClick={handleLogout}
              >
                Sign out
              </button>
            </div>
          )}
        </div>

        <button
          type="button"
          className="menu-toggle"
          aria-label="Menu"
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((open) => !open)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d={mobileOpen ? "M6 6l12 12M18 6L6 18" : "M4 7h16M4 12h16M4 17h16"}
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {mobileOpen && (
        <nav className="mobile-nav">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={navLinkClass}
            >
              {link.label}
            </NavLink>
          ))}
          <NavLink to="/account" className={navLinkClass}>
            Account settings
          </NavLink>
          <button
            type="button"
            className="nav-link button-ghost"
            style={{ border: "none", textAlign: "left", cursor: "pointer" }}
            onClick={handleLogout}
          >
            Sign out ({user?.email})
          </button>
        </nav>
      )}
    </header>
  );
}


export default NavBar;
