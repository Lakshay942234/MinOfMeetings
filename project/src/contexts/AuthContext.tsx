import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface User {
  id: string;
  displayName: string;
  mail: string;
}

interface AuthContextType {
  isAuthenticated: boolean;
  user: User | null;
  login: () => void;
  logout: () => void;
  loading: boolean;
  error: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Handle backend-driven redirect: /auth/signed-in?user_id=...
    const params = new URLSearchParams(window.location.search);
    const uid = params.get('user_id');
    const displayNameParam = params.get('displayName');
    const mailParam = params.get('mail');
    if (uid) {
      try {
        localStorage.setItem('userId', uid);
        if (displayNameParam) localStorage.setItem('userDisplayName', displayNameParam);
        if (mailParam) localStorage.setItem('userMail', mailParam);
      } catch {}
      // Validate session on backend, then clear URL params
      checkAuthStatus().finally(() => {
        window.history.replaceState({}, document.title, '/');
      });
      return;
    }

    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const userId = localStorage.getItem('userId');
      if (!userId) {
        setLoading(false);
        return;
      }

      const response = await fetch(`http://localhost:8000/api/auth/status/${userId}`);
      const data = await response.json();

      if (data.authenticated) {
        setIsAuthenticated(true);
        setUser({
          id: userId,
          displayName: localStorage.getItem('userDisplayName') || localStorage.getItem('userMail') || userId,
          mail: localStorage.getItem('userMail') || ''
        });
      } else {
        // Try to refresh token
        if (data.needs_refresh) {
          await refreshToken(userId);
        } else {
          logout();
        }
      }
    } catch (error) {
      console.error('Error checking auth status:', error);
      setError('Failed to verify authentication status');
    } finally {
      setLoading(false);
    }
  };

  const refreshToken = async (userId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/auth/refresh?user_id=${encodeURIComponent(userId)}`, {
        method: 'POST',
      });

      if (response.ok) {
        setIsAuthenticated(true);
        setUser({
          id: userId,
          displayName: localStorage.getItem('userDisplayName') || userId,
          mail: localStorage.getItem('userMail') || ''
        });
      } else {
        logout();
      }
    } catch (error) {
      console.error('Error refreshing token:', error);
      logout();
    }
  };

  const login = async () => {
    try {
      setLoading(true);
      setError(null);

      // Get authorization URL
      const response = await fetch('http://localhost:8000/api/auth/login');
      const data = await response.json();

      if (data.auth_url) {
        // Redirect to Microsoft login
        window.location.href = data.auth_url;
      } else {
        throw new Error('Failed to get authorization URL');
      }
    } catch (error) {
      console.error('Login error:', error);
      setError('Failed to initiate login process');
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('userId');
    localStorage.removeItem('userDisplayName');
    localStorage.removeItem('userMail');
    setIsAuthenticated(false);
    setUser(null);
    setError(null);
  };

  // Handle OAuth callback
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const error = urlParams.get('error');

    if (error) {
      setError(`Authentication failed: ${error}`);
      setLoading(false);
      return;
    }

    if (code && !isAuthenticated) {
      handleOAuthCallback(code);
    }
  }, [isAuthenticated]);

  const handleOAuthCallback = async (code: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/auth/callback?code=${code}`);
      const data = await response.json();

      if (response.ok && data.user) {
        localStorage.setItem('userId', data.user.id);
        localStorage.setItem('userDisplayName', data.user.displayName);
        localStorage.setItem('userMail', data.user.mail);

        setUser(data.user);
        setIsAuthenticated(true);
        
        // Clear URL parameters
        window.history.replaceState({}, document.title, window.location.pathname);
      } else {
        throw new Error(data.detail || 'Authentication failed');
      }
    } catch (error) {
      console.error('OAuth callback error:', error);
      setError(`Authentication failed: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const value = {
    isAuthenticated,
    user,
    login,
    logout,
    loading,
    error
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};