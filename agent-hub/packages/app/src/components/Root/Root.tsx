import { PropsWithChildren, useEffect } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import SettingsOutlined from '@material-ui/icons/SettingsOutlined';

export const Root = ({ children }: PropsWithChildren<{}>) => {
  const { pathname } = useLocation();
  useEffect(() => {
    if (pathname === '/catalog') document.title = 'Agents | Aiven Agent Hub';
    if (pathname === '/create') document.title = 'Create an agent | Aiven Agent Hub';
  }, [pathname]);
  return <div className={`hub-app${pathname.startsWith('/create') ? ' hub-create' : ''}`}>
    <a className="hub-skip-link" href="#hub-content">Skip to content</a>
    <header className="hub-topbar">
      <div className="hub-topbar-inner">
        <Link to="/catalog" className="hub-brand" aria-label="Aiven Agent Hub home">
          <img src="/brand/logo-aiven-white.svg" alt="Aiven" width="110" height="37" />
          <span className="hub-brand-divider" />
          <span className="hub-brand-title">Agent Hub</span>
        </Link>
        <nav className="hub-navigation" aria-label="Main navigation">
          <NavLink to="/catalog">Agents</NavLink>
          <NavLink to="/create">Create an agent</NavLink>
        </nav>
        <div className="hub-topbar-end">
          <span className="hub-workspace-label">Aiven Platform</span>
          <NavLink to="/settings" className="hub-settings" aria-label="Settings"><SettingsOutlined fontSize="small" /></NavLink>
        </div>
      </div>
    </header>
    <div id="hub-content" className="hub-content" tabIndex={-1}>{children}</div>
    <footer className="hub-footer"><span>Built with open source. Powered by Aiven.</span><span>Agent Hub · Backstage</span></footer>
  </div>;
};
