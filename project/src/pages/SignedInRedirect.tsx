import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const SignedInRedirect: React.FC = () => {
  const { loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // Once AuthContext finishes processing (loading becomes false),
    // navigate to the app root. AuthContext already set auth state.
    if (!loading) {
      navigate('/', { replace: true });
    }
  }, [loading, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="loading-spinner w-8 h-8 mx-auto mb-4"></div>
        <p className="text-gray-600">Completing sign-in…</p>
      </div>
    </div>
  );
};

export default SignedInRedirect;
