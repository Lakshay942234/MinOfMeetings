import React from 'react';
import { Calendar, Users, BarChart, CheckSquare } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

const Login: React.FC = () => {
  const { login, loading, error } = useAuth();

  const features = [
    {
      icon: Calendar,
      title: 'Automatic Meeting Capture',
      description: 'Automatically sync your Microsoft Teams meetings and extract transcripts for processing.'
    },
    {
      icon: Users,
      title: 'AI-Powered MOM Generation',
      description: 'Generate structured Minutes of Meeting using advanced AI to identify key decisions and action items.'
    },
    {
      icon: CheckSquare,
      title: 'Task Assignment',
      description: 'Automatically assign action items to team members via Microsoft Planner or email notifications.'
    },
    {
      icon: BarChart,
      title: 'Meeting Analytics',
      description: 'Track meeting costs, time spent, and productivity metrics across your organization.'
    }
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-white">
      <div className="flex">
        {/* Left side - Features */}
        <div className="hidden lg:flex lg:w-1/2 flex-col justify-center px-12 py-24">
          <div className="max-w-md">
            <div className="flex items-center space-x-3 mb-8">
              <Calendar className="h-10 w-10 text-blue-600" />
              <h1 className="text-2xl font-bold text-gray-900">
                MOM Automation Tool
              </h1>
            </div>
            
            <p className="text-lg text-gray-600 mb-8">
              Streamline your meeting workflow with AI-powered Minutes of Meeting generation 
              and automatic task assignment.
            </p>

            <div className="space-y-6">
              {features.map((feature, index) => {
                const Icon = feature.icon;
                return (
                  <div key={index} className="flex items-start space-x-4 animate-fade-in" 
                       style={{ animationDelay: `${index * 0.1}s` }}>
                    <div className="flex-shrink-0">
                      <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                        <Icon className="h-6 w-6 text-blue-600" />
                      </div>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900 mb-1">
                        {feature.title}
                      </h3>
                      <p className="text-sm text-gray-600">
                        {feature.description}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right side - Login */}
        <div className="flex-1 flex flex-col justify-center py-24 px-6 sm:px-12 lg:px-16">
          <div className="max-w-md w-full mx-auto">
            {/* Mobile header */}
            <div className="lg:hidden text-center mb-8">
              <div className="flex items-center justify-center space-x-3 mb-4">
                <Calendar className="h-10 w-10 text-blue-600" />
                <h1 className="text-2xl font-bold text-gray-900">
                  MOM Automation Tool
                </h1>
              </div>
              <p className="text-gray-600">
                AI-powered meeting management for Microsoft Teams
              </p>
            </div>

            <div className="card">
              <div className="text-center mb-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                  Sign in to continue
                </h2>
                <p className="text-gray-600">
                  Connect with your Microsoft account to get started
                </p>
              </div>

              {error && (
                <ErrorAlert 
                  message={error} 
                  className="mb-6"
                />
              )}

              <button
                onClick={login}
                disabled={loading}
                className="w-full flex items-center justify-center px-4 py-3 border border-transparent rounded-lg shadow-sm text-base font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <div className="flex items-center space-x-3">
                    <LoadingSpinner size="sm" />
                    <span>Connecting...</span>
                  </div>
                ) : (
                  <div className="flex items-center space-x-3">
                    <svg className="w-5 h-5" viewBox="0 0 23 23">
                      <path fill="#f3f3f3" d="M0 0h23v23H0z"/>
                      <path fill="#f35325" d="M1 1h10v10H1z"/>
                      <path fill="#81bc06" d="M12 1h10v10H12z"/>
                      <path fill="#05a6f0" d="M1 12h10v10H1z"/>
                      <path fill="#ffba08" d="M12 12h10v10H12z"/>
                    </svg>
                    <span>Sign in with Microsoft</span>
                  </div>
                )}
              </button>

              <div className="mt-6 text-center">
                <p className="text-xs text-gray-500">
                  By signing in, you agree to our terms of service and privacy policy.
                  This application requires Microsoft Teams and Office 365 access.
                </p>
              </div>
            </div>

            {/* Security notice */}
            <div className="mt-8 p-4 bg-blue-50 rounded-lg">
              <div className="flex items-start space-x-3">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                    <Calendar className="h-5 w-5 text-blue-600" />
                  </div>
                </div>
                <div>
                  <h4 className="text-sm font-medium text-blue-900 mb-1">
                    Secure Integration
                  </h4>
                  <p className="text-xs text-blue-700">
                    This application uses Microsoft Graph API with secure OAuth2 authentication. 
                    Your credentials are never stored, and all data access follows Microsoft security standards.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;