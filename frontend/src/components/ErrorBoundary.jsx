import { Component } from "react";
import { Icon } from "./Icon";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error("Butterlane interface error", error);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="error-screen">
        <div className="error-screen__card glass-panel">
          <span className="error-screen__icon"><Icon name="alert" size={24} /></span>
          <p className="eyebrow">PLEASE RELOAD</p>
          <h1>This screen needs to reload.</h1>
          <p>Your bakery records were not changed. Reload to continue.</p>
          <button className="button button--primary" onClick={() => window.location.reload()}>Reload</button>
        </div>
      </main>
    );
  }
}
