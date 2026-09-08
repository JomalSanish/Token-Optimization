import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import styles from './Layout.module.css';

export default function AdminLayout() {
  return (
    <div className={styles.layoutContainer}>
      <aside className={styles.sidebar}>
        <div className={styles.logoArea}>
          <h1>Admin Portal</h1>
        </div>
        <nav className={styles.nav}>
          <NavLink
            to="/admin/providers"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Providers
          </NavLink>
          <NavLink
            to="/admin/models"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Models
          </NavLink>
          <NavLink
            to="/admin/pricing"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Pricing
          </NavLink>
          <NavLink
            to="/admin/rules"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Rules
          </NavLink>
          <NavLink
            to="/admin/phases"
            className={({ isActive }) => 
              isActive ? `${styles.navLink} ${styles.activeNavLink}` : styles.navLink
            }
          >
            Phases
          </NavLink>
        </nav>
      </aside>
      <main className={styles.mainContent}>
        <Outlet />
      </main>
    </div>
  );
}
