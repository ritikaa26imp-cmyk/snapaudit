import { NavLink, Outlet } from 'react-router-dom';

const navLinkStyle = ({ isActive }) => ({
  padding: '12px 18px',
  borderRadius: 8,
  textDecoration: 'none',
  fontSize: 14,
  fontWeight: 500,
  color: isActive ? '#0f172a' : '#64748b',
  background: isActive ? '#e2e8f0' : 'transparent',
});

const barStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '18px 32px',
  minHeight: 60,
  background: '#fff',
  borderBottom: '1px solid #e2e8f0',
  position: 'sticky',
  top: 0,
  zIndex: 10,
  boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
};

const brandStyle = {
  fontSize: 18,
  fontWeight: 700,
  color: '#0f172a',
  letterSpacing: '-0.02em',
};

const navStyle = { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };

const mainStyle = { maxWidth: 1120, margin: '0 auto', padding: '36px 32px 48px' };

/**
 * Shell: brand + nav with active state, then nested routes.
 */
export default function Layout() {
  return (
    <>
      <header style={barStyle}>
        <span style={brandStyle}>SnapAudit</span>
        <nav style={navStyle}>
          <NavLink to="/" end style={navLinkStyle}>
            Compare
          </NavLink>
          <NavLink to="/bulk" style={navLinkStyle}>
            Bulk
          </NavLink>
          <NavLink to="/audits" style={navLinkStyle}>
            Audit Log
          </NavLink>
          <NavLink to="/visibility" style={navLinkStyle}>
            Visibility Check
          </NavLink>
          <NavLink to="/policy" style={navLinkStyle}>
            Policy
          </NavLink>
        </nav>
      </header>
      <main style={mainStyle}>
        <Outlet />
      </main>
    </>
  );
}
