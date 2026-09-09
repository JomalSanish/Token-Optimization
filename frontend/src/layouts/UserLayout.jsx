import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import styles from './Layout.module.css';

export default function UserLayout() {
  return (
    <div className={styles.layoutContainer}>
      <aside className={styles.sidebar}>
        <div className={styles.logoArea}>
          <h1>Token Optimizer</h1>
        </div>
        <nav className={styles.nav}>
          <NavLink
            to="/keys"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            API Keys
          </NavLink>
          <NavLink
            to="/project"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Project
          </NavLink>
          <NavLink
            to="/estimate"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Estimate
          </NavLink>
          <NavLink
            to="/optimize"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Optimize
          </NavLink>
          <NavLink
            to="/discover"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Discover
          </NavLink>
        </nav>
        <div style={{ marginTop: 'auto', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
          <NavLink
            to="/admin"
            className={styles.navLink}
            style={{ fontSize: '13px', opacity: 0.8 }}
          >
            ⚙️ Admin Portal
          </NavLink>
        </div>
      </aside>
      <main className={styles.mainContent}>
        <Outlet />
      </main>
    </div>
  );
}
