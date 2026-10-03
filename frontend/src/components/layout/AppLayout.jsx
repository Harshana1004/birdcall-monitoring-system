import { Outlet } from "react-router-dom";

import NavBar from "./NavBar";


function AppLayout() {
  return (
    <div className="app-shell">
      <NavBar />

      <Outlet />

      <footer className="footer">
        <div className="footer-inner">
          <span>AvianAcoustics · Bird-call monitoring</span>
          <span>Species identification by BirdNET</span>
        </div>
      </footer>
    </div>
  );
}


export default AppLayout;
