import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Navigation from './components/Navigation';
import Dashboard from './pages/Dashboard';
import Meetings from './pages/Meetings';
import Analytics from './pages/Analytics';
import Tasks from './pages/Tasks';
import Login from './pages/Login';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ApiProvider } from './contexts/ApiContext';
import SignedInRedirect from './pages/SignedInRedirect';

function AppContent() {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center space-y-4">
          <div className="loading-spinner w-8 h-8"></div>
          <p className="text-gray-600">Loading application...</p>
        </div>
      </div>
    );
  }

  // During OAuth redirect, show a dedicated page so AuthContext can process query params.
  if (location.pathname === '/auth/signed-in') {
    return <SignedInRedirect />;
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation />
      <main className="ml-0 lg:ml-64 p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/meetings" element={<Meetings />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <ApiProvider>
          <AppContent />
        </ApiProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;