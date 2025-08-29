import React, { useState, useEffect } from 'react';
import { Calendar, Clock, Users, TrendingUp, CheckSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useApi } from '../contexts/ApiContext';
import { useAuth } from '../contexts/AuthContext';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

interface DashboardStats {
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
  has_transcript?: boolean;
  transcript_text?: string;
  transcription_status?: string;
  transcription_method?: string;
  mom_generated?: boolean;
}

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentMeetings, setRecentMeetings] = useState<RecentMeeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const api = useApi();
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    loadDashboardData();
    
    // Auto-refresh every 30 seconds to update meeting statuses
    const interval = setInterval(() => {
      loadDashboardData();
    }, 30000);
    
    return () => clearInterval(interval);
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load recent meetings
      const meetingsResponse = await api.get('/meetings?limit=5');
      setRecentMeetings(meetingsResponse.meetings);
      
      // Load analytics stats to match analytics page
      try {
        const analyticsResponse = await api.get('/analytics/summary');
        setStats(analyticsResponse.summary);
      } catch (analyticsError) {
        // Fallback: calculate stats from all meetings if analytics endpoint fails
        console.warn('Analytics endpoint failed, calculating from meetings data');
        const allMeetingsResponse = await api.get('/meetings');
        const allMeetings = allMeetingsResponse.meetings || [];
        
        const totalMinutes = allMeetings.reduce((acc: number, m: any) => acc + (m.duration_minutes || 0), 0);
        const totalHours = Math.round(totalMinutes / 60);
        const uniqueParticipants = new Set(allMeetings.flatMap((m: any) => 
          (m.participants_json || []).map((p: any) => p.email || p.name)
        )).size;
        
        // Calculate cost based on average hourly rate (₹500 per participant per hour)
        const avgParticipantsPerMeeting = allMeetings.length > 0 ? 
          allMeetings.reduce((acc: number, m: any) => acc + (m.participants_count || 0), 0) / allMeetings.length : 0;
        const estimatedCost = Math.round(totalHours * avgParticipantsPerMeeting * 500);
        
        setStats({
          total_meetings: allMeetings.length,
          total_hours: totalHours,
          total_cost: estimatedCost,
          unique_participants: uniqueParticipants,
          avg_participants: Math.round(avgParticipantsPerMeeting),
          departments_involved: 0
        });
      }

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
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex items-center justify-center min-h-96"
      >
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-gray-600">Loading dashboard...</p>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-8"
    >
      {/* Header */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0"
      >
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 bg-clip-text text-transparent">
            Dashboard
          </h1>
          <p className="text-gray-600 mt-1">Welcome back, {user?.mail || user?.displayName || user?.id}</p>
        </div>
        
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleSyncMeetings}
          disabled={syncing}
          className="relative px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-2xl font-medium shadow-lg hover:shadow-xl transition-all duration-200 flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-blue-700 to-blue-800 opacity-0 hover:opacity-100 transition-opacity duration-200" />
          <div className="relative flex items-center space-x-2">
            {syncing ? (
              <>
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  <span className="text-sm">₹</span>
                </motion.div>
                <span>Syncing...</span>
              </>
            ) : (
              <>
                <Calendar className="h-4 w-4" />
                <span>Sync Meetings</span>
              </>
            )}
          </div>
        </motion.button>
      </motion.div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
          >
            <ErrorAlert message={error} onClose={() => setError(null)} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Summary Cards */}
      {stats && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
        >
          {[
            {
              icon: Calendar,
              label: 'Total Meetings',
              value: stats.total_meetings,
              gradient: 'from-blue-500 to-blue-600',
              bgGradient: 'from-blue-50 to-blue-100',
              delay: 0.3
            },
            {
              icon: Clock,
              label: 'Total Hours',
              value: stats.total_hours,
              gradient: 'from-emerald-500 to-emerald-600',
              bgGradient: 'from-emerald-50 to-emerald-100',
              delay: 0.4
            },
            {
              icon: TrendingUp,
              label: 'Meeting Cost',
              value: stats.total_cost,
              gradient: 'from-amber-500 to-amber-600',
              bgGradient: 'from-amber-50 to-amber-100',
              delay: 0.5,
              isCurrency: true
            },
            {
              icon: Users,
              label: 'Unique Participants',
              value: stats.unique_participants,
              gradient: 'from-purple-500 to-purple-600',
              bgGradient: 'from-purple-50 to-purple-100',
              delay: 0.6
            }
          ].map((stat) => {
            const IconComponent = stat.icon;
            return (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: stat.delay }}
                whileHover={{ y: -4, transition: { duration: 0.2 } }}
                className="group cursor-pointer"
              >
                <div className="relative bg-white rounded-2xl p-6 shadow-sm hover:shadow-xl transition-all duration-300 border border-gray-100 overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-br opacity-0 group-hover:opacity-5 transition-opacity duration-300" />
                  <div className="flex items-center">
                    <div className="flex-shrink-0">
                      <div className={`w-12 h-12 bg-gradient-to-br ${stat.bgGradient} rounded-2xl flex items-center justify-center shadow-sm`}>
                        <div className={`w-8 h-8 bg-gradient-to-br ${stat.gradient} rounded-xl flex items-center justify-center`}>
                          <IconComponent className="h-4 w-4 text-white" />
                        </div>
                      </div>
                    </div>
                    <div className="ml-4 flex-1">
                      <p className="text-sm font-medium text-gray-600 mb-1">{stat.label}</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {stat.isCurrency ? `₹${stat.value.toLocaleString()}` : stat.value.toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      )}

      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.7 }}
        className="grid grid-cols-1 lg:grid-cols-3 gap-8"
      >
        {/* Recent Meetings */}
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.8 }}
          className="lg:col-span-2"
        >
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-gray-900">Recent Meetings</h3>
              <motion.a 
                href="/meetings" 
                whileHover={{ scale: 1.05 }}
                className="text-sm text-blue-600 hover:text-blue-700 font-medium px-3 py-1 rounded-lg hover:bg-blue-50 transition-colors"
              >
                View all
              </motion.a>
            </div>
            
            {recentMeetings.length === 0 ? (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-center py-12"
              >
                <div className="w-16 h-16 bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Calendar className="h-8 w-8 text-gray-400" />
                </div>
                <p className="text-gray-600 font-medium">No meetings found</p>
                <p className="text-sm text-gray-500 mt-2">
                  Click "Sync Meetings" to import your Teams meetings
                </p>
              </motion.div>
            ) : (
              <div className="space-y-3">
                {recentMeetings.map((meeting, index) => (
                  <motion.div 
                    key={meeting.meeting_id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.9 + index * 0.1 }}
                    whileHover={{ scale: 1.01, transition: { duration: 0.2 } }}
                    onClick={() => navigate('/meetings')}
                    className="group cursor-pointer p-4 bg-gradient-to-r from-gray-50 to-gray-50/50 rounded-2xl hover:from-blue-50 hover:to-blue-50/50 transition-all duration-200 border border-gray-100 hover:border-blue-200"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-900 truncate group-hover:text-blue-900 transition-colors">
                          {meeting.title}
                        </p>
                        <div className="flex items-center space-x-3 mt-2">
                          <div className="flex items-center space-x-1">
                            <Clock className="h-3 w-3 text-gray-400" />
                            <p className="text-xs text-gray-500">
                              {formatDate(meeting.date)}
                            </p>
                          </div>
                          <div className="flex items-center space-x-1">
                            <div className="w-1 h-1 bg-gray-300 rounded-full" />
                            <p className="text-xs text-gray-500">
                              {meeting.duration_minutes} min
                            </p>
                          </div>
                          <div className="flex items-center space-x-1">
                            <Users className="h-3 w-3 text-gray-400" />
                            <p className="text-xs text-gray-500">
                              {meeting.participants_count}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2 ml-4">
                        {(() => {
                          const meetingDate = new Date(meeting.date);
                          const now = new Date();
                          const hasTranscript = meeting.has_transcript || (meeting.transcript_text && meeting.transcript_text.length > 100);
                          const hasMOM = meeting.has_mom || meeting.mom_generated;
                          
                          // Meeting hasn't happened yet
                          if (meetingDate > now) {
                            return (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 border border-gray-200">
                                <div className="w-1.5 h-1.5 bg-gray-500 rounded-full mr-1.5" />
                                Scheduled
                              </span>
                            );
                          }
                          
                          // Meeting happened, check status
                          if (hasMOM) {
                            return (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                                <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5" />
                                MOM Generated
                              </span>
                            );
                          } else if (hasTranscript) {
                            return (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800 border border-purple-200">
                                <div className="w-1.5 h-1.5 bg-purple-500 rounded-full mr-1.5" />
                                Generate MOM
                              </span>
                            );
                          } else {
                            return (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">
                                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full mr-1.5 animate-pulse" />
                                Waiting
                              </span>
                            );
                          }
                        })()}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* Quick Actions & System Status */}
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.9 }}
          className="space-y-6"
        >
          {/* Quick Actions */}
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <h3 className="text-xl font-bold text-gray-900 mb-6">Quick Actions</h3>
            <div className="space-y-3">
              {[
                {
                  href: '/meetings',
                  icon: Calendar,
                  label: 'View All Meetings',
                  gradient: 'from-blue-500 to-blue-600',
                  bgGradient: 'from-blue-50 to-blue-100',
                  hoverBg: 'hover:from-blue-100 hover:to-blue-150',
                  delay: 1.0
                },
                {
                  href: '/analytics',
                  icon: TrendingUp,
                  label: 'View Analytics',
                  gradient: 'from-emerald-500 to-emerald-600',
                  bgGradient: 'from-emerald-50 to-emerald-100',
                  hoverBg: 'hover:from-emerald-100 hover:to-emerald-150',
                  delay: 1.1
                },
                {
                  href: '/tasks',
                  icon: CheckSquare,
                  label: 'Manage Tasks',
                  gradient: 'from-purple-500 to-purple-600',
                  bgGradient: 'from-purple-50 to-purple-100',
                  hoverBg: 'hover:from-purple-100 hover:to-purple-150',
                  delay: 1.2
                }
              ].map((action) => {
                const IconComponent = action.icon;
                return (
                  <motion.a
                    key={action.href}
                    href={action.href}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: action.delay }}
                    whileHover={{ scale: 1.02, transition: { duration: 0.2 } }}
                    whileTap={{ scale: 0.98 }}
                    className={`block p-4 bg-gradient-to-r ${action.bgGradient} ${action.hoverBg} rounded-2xl transition-all duration-200 border border-gray-100 group`}
                  >
                    <div className="flex items-center">
                      <div className={`w-10 h-10 bg-gradient-to-br ${action.gradient} rounded-xl flex items-center justify-center shadow-sm mr-4 group-hover:shadow-md transition-shadow`}>
                        <IconComponent className="h-5 w-5 text-white" />
                      </div>
                      <span className="text-sm font-semibold text-gray-800 group-hover:text-gray-900 transition-colors">{action.label}</span>
                    </div>
                  </motion.a>
                );
              })}
            </div>
          </div>

          {/* System Status */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.3 }}
            className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100"
          >
            <h3 className="text-xl font-bold text-gray-900 mb-6">System Status</h3>
            <div className="space-y-4">
              {[
                { label: 'Microsoft Graph API', status: 'Connected' },
                { label: 'AI Service', status: 'Active' },
                { label: 'Database', status: 'Healthy' }
              ].map((item, index) => (
                <motion.div 
                  key={item.label}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 1.4 + index * 0.1 }}
                  className="flex items-center justify-between p-3 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="text-sm font-medium text-gray-700">{item.label}</span>
                  <div className="flex items-center space-x-2">
                    <motion.div
                      animate={{ scale: [1, 1.2, 1] }}
                      transition={{ duration: 2, repeat: Infinity }}
                      className="w-2 h-2 bg-emerald-500 rounded-full"
                    />
                    <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2 py-1 rounded-full border border-emerald-200">
                      {item.status}
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      </motion.div>
    </motion.div>
  );
};

export default Dashboard;