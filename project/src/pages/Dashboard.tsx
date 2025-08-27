import React, { useState, useEffect } from 'react';
import { Calendar, Users, Clock, IndianRupee, TrendingUp, CheckSquare, AlertCircle } from 'lucide-react';
import { useApi } from '../contexts/ApiContext';
import { useAuth } from '../contexts/AuthContext';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

interface SummaryStats {
  total_meetings: number;
  total_hours: number;
  total_cost: number;
  unique_participants: number;
  avg_participants: number;
  departments_involved: number;
}

interface RecentMeeting {
  meeting_id: string;
  title: string;
  date: string;
  duration_minutes: number;
  participants_count: number;
  has_mom: boolean;
}

const Dashboard: React.FC = () => {
  const [summaryStats, setSummaryStats] = useState<SummaryStats | null>(null);
  const [recentMeetings, setRecentMeetings] = useState<RecentMeeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const api = useApi();
  const { user } = useAuth();

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load summary statistics
      const summaryResponse = await api.get('/analytics/summary');
      setSummaryStats(summaryResponse.summary);

      // Load recent meetings
      const meetingsResponse = await api.get('/meetings?limit=5');
      setRecentMeetings(meetingsResponse.meetings);

    } catch (error) {
      console.error('Error loading dashboard:', error);
      setError(`Failed to load dashboard data: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSyncMeetings = async () => {
    if (!user) return;

    try {
      setSyncing(true);
      setError(null);

      const response = await api.post(`/meetings/sync/${user.id}?days_back=7`);
      
      // Reload dashboard data after sync
      await loadDashboardData();

      // Show success message (you could implement a toast notification here)
      console.log(`Synced ${response.synced_count} meetings`);

    } catch (error) {
      console.error('Error syncing meetings:', error);
      setError(`Failed to sync meetings: ${error}`);
    } finally {
      setSyncing(false);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600">Welcome back, {user?.mail || user?.displayName || user?.id}</p>
        </div>
        
        <button
          onClick={handleSyncMeetings}
          disabled={syncing}
          className="btn-primary flex items-center space-x-2"
        >
          {syncing ? (
            <>
              <LoadingSpinner size="sm" />
              <span>Syncing...</span>
            </>
          ) : (
            <>
              <Calendar className="h-4 w-4" />
              <span>Sync Meetings</span>
            </>
          )}
        </button>
      </div>

      {error && (
        <ErrorAlert message={error} onClose={() => setError(null)} />
      )}

      {/* Summary Cards */}
      {summaryStats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Calendar className="h-6 w-6 text-blue-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Total Meetings</p>
                <p className="text-2xl font-semibold text-gray-900">{summaryStats.total_meetings}</p>
              </div>
            </div>
          </div>

          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <Clock className="h-6 w-6 text-green-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Total Hours</p>
                <p className="text-2xl font-semibold text-gray-900">{summaryStats.total_hours}</p>
              </div>
            </div>
          </div>

          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center">
                  <IndianRupee className="h-6 w-6 text-yellow-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Meeting Cost</p>
                <p className="text-2xl font-semibold text-gray-900">{formatCurrency(summaryStats.total_cost)}</p>
              </div>
            </div>
          </div>

          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                  <Users className="h-6 w-6 text-purple-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Unique Participants</p>
                <p className="text-2xl font-semibold text-gray-900">{summaryStats.unique_participants}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Meetings */}
        <div className="lg:col-span-2">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Recent Meetings</h3>
              <a href="/meetings" className="text-sm text-blue-600 hover:text-blue-700 font-medium">
                View all
              </a>
            </div>
            
            {recentMeetings.length === 0 ? (
              <div className="text-center py-8">
                <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">No meetings found</p>
                <p className="text-sm text-gray-400 mt-1">
                  Click "Sync Meetings" to import your Teams meetings
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {recentMeetings.map((meeting, index) => (
                  <div key={meeting.meeting_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors animate-slide-in"
                       style={{ animationDelay: `${index * 0.1}s` }}>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {meeting.title}
                      </p>
                      <div className="flex items-center space-x-2 mt-1">
                        <p className="text-xs text-gray-500">
                          {formatDate(meeting.date)}
                        </p>
                        <span className="text-xs text-gray-300">•</span>
                        <p className="text-xs text-gray-500">
                          {meeting.duration_minutes} min
                        </p>
                        <span className="text-xs text-gray-300">•</span>
                        <p className="text-xs text-gray-500">
                          {meeting.participants_count} participants
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2 ml-4">
                      {meeting.has_mom ? (
                        <span className="status-success">
                          MOM Generated
                        </span>
                      ) : (
                        <span className="status-warning">
                          Pending
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="space-y-6">
          <div className="card">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h3>
            <div className="space-y-3">
              <a
                href="/meetings"
                className="block p-3 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors"
              >
                <div className="flex items-center">
                  <Calendar className="h-5 w-5 text-blue-600 mr-3" />
                  <span className="text-sm font-medium text-blue-900">View All Meetings</span>
                </div>
              </a>
              
              <a
                href="/analytics"
                className="block p-3 bg-green-50 hover:bg-green-100 rounded-lg transition-colors"
              >
                <div className="flex items-center">
                  <TrendingUp className="h-5 w-5 text-green-600 mr-3" />
                  <span className="text-sm font-medium text-green-900">View Analytics</span>
                </div>
              </a>
              
              <a
                href="/tasks"
                className="block p-3 bg-purple-50 hover:bg-purple-100 rounded-lg transition-colors"
              >
                <div className="flex items-center">
                  <CheckSquare className="h-5 w-5 text-purple-600 mr-3" />
                  <span className="text-sm font-medium text-purple-900">Manage Tasks</span>
                </div>
              </a>
            </div>
          </div>

          {/* System Status */}
          <div className="card">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">System Status</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Microsoft Graph API</span>
                <span className="status-success">Connected</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">AI Service</span>
                <span className="status-success">Active</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Database</span>
                <span className="status-success">Healthy</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;