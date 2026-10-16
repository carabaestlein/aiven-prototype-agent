import { PropsWithChildren } from 'react';
import HomeIcon from '@material-ui/icons/Home';
import AddCircleOutline from '@material-ui/icons/AddCircleOutline';
import SettingsIcon from '@material-ui/icons/Settings';
import { Sidebar, SidebarDivider, SidebarItem, SidebarPage, SidebarSpace, Link } from '@backstage/core-components';
export const Root = ({ children }: PropsWithChildren<{}>) => <SidebarPage>
  <Sidebar>
    <Link to="/" style={{ color: 'white', padding: 20, fontWeight: 700, fontSize: 18 }}>Agent Hub</Link>
    <SidebarDivider />
    <SidebarItem icon={HomeIcon} to="catalog" text="Agents" />
    <SidebarItem icon={AddCircleOutline} to="create" text="New agent" />
    <SidebarSpace />
    <SidebarItem icon={SettingsIcon} to="settings" text="Settings" />
  </Sidebar>
  {children}
</SidebarPage>;
