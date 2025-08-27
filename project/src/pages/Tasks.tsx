import React, { useState, useEffect } from 'react';
import { CheckSquare, Clock, User, AlertCircle, Send, Eye } from 'lucide-react';
import { useApi } from '../contexts/ApiContext';
import { useAuth } from '../contexts/AuthContext';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

interface ActionItem {
  task: string;
  assigned_to: string;
  due_date: string;
  priority: 'high' | 'medium' | 'low';
}

interface Meeting {
  meeting_id: string;
  meeting_title: string;
  action_items: ActionItem[];
  total_items: number;
}

interface PersistedTask {
  id: number;
  meeting_id: string;
  task: string;
  assigned_to: string;
  assignee_name?: string;
  due_date?: string | null;
  priority: 'high' | 'medium' | 'low' | string;
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | string;
  source?: string;
  external_id?: string | null;
}

interface TaskMetrics {
  total_meetings_with_tasks: number;
  total_action_items: number;
  priority_distribution: {
    high: number;
    medium: number;
    low: number;
  };
  top_assignees: Array<{
    assignee: string;
    task_count: number;
  }>;
  unique_assignees: number;
}

const Tasks: React.FC = () => {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const [metrics, setMetrics] = useState<TaskMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assignmentResult, setAssignmentResult] = useState<any>(null);
  const [assignToAll, setAssignToAll] = useState(false);
  const [meetingTasks, setMeetingTasks] = useState<PersistedTask[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [updatingTaskId, setUpdatingTaskId] = useState<number | null>(null);

  const api = useApi();
  const { user } = useAuth();

  useEffect(() => {
    loadTaskData();
  }, []);

  const loadTaskData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load meetings data
      const meetingsResponse = await api.get('/meetings?limit=50');
      const meetingsWithTasks = meetingsResponse.meetings.filter((m: any) => m.has_mom);
      
      // Get action items for each meeting
      const meetingsData = await Promise.all(
        meetingsWithTasks.map(async (meeting: any) => {
          try {
            const actionItemsResponse = await api.get(`/tasks/action-items/${meeting.meeting_id}`);
            return actionItemsResponse;
          } catch (error) {
            console.warn(`Could not load action items for meeting ${meeting.meeting_id}`);
            return null;
          }
        })
      );

      const validMeetings = meetingsData.filter(Boolean);
      setMeetings(validMeetings);

      // Load task metrics
      const metricsResponse = await api.get('/tasks/metrics');
      setMetrics(metricsResponse);

    } catch (error) {
      console.error('Error loading task data:', error);
      setError(`Failed to load task data: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const onSelectMeeting = async (meeting: Meeting) => {
    setSelectedMeeting(meeting);
    await loadMeetingTasks(meeting.meeting_id);
  };

  const loadMeetingTasks = async (meetingId: string) => {
    try {
      setLoadingTasks(true);
      const resp = await api.get(`/tasks/by-meeting/${meetingId}`);
      setMeetingTasks(resp.tasks || []);
    } catch (e) {
      console.error('Failed to load meeting tasks', e);
    } finally {
      setLoadingTasks(false);
    }
  };

  const assignTasks = async (meetingId: string) => {
    if (!user) return;

    try {
      setAssigning(true);
      setError(null);
      setAssignmentResult(null);

      const response = await api.post(`/tasks/assign/${meetingId}?assign_to_all=${assignToAll}`, { user_id: user.id });
      setAssignmentResult(response);

      // Reload metrics after assignment
      const metricsResponse = await api.get('/tasks/metrics');
      setMetrics(metricsResponse);

      // Reload meeting tasks
      await loadMeetingTasks(meetingId);

    } catch (error) {
      console.error('Error assigning tasks:', error);
      setError(`Failed to assign tasks: ${error}`);
    } finally {
      setAssigning(false);
    }
  };

  const updateTaskStatus = async (taskId: number, status: 'pending' | 'in_progress' | 'completed' | 'blocked') => {
    try {
      setUpdatingTaskId(taskId);
      await api.put(`/tasks/status/${taskId}`, { status });
      setMeetingTasks(prev => prev.map(t => t.id === taskId ? { ...t, status } : t));
    } catch (e) {
      console.error('Failed to update task status', e);
      setError('Failed to update task status');
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'bg-red-100 text-red-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      case 'low':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return 'No due date';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'blocked':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-gray-600">Loading tasks...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Task Management</h1>
          <p className="text-gray-600">Manage action items from meeting MOMs</p>
        </div>
      </div>

      {error && (
        <ErrorAlert message={error} onClose={() => setError(null)} />
      )}

      {/* Metrics Cards */}
      {metrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <CheckSquare className="h-6 w-6 text-blue-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Total Action Items</p>
                <p className="text-2xl font-semibold text-gray-900">{metrics.total_action_items}</p>
              </div>
            </div>
          </div>

          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <User className="h-6 w-6 text-green-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Unique Assignees</p>
                <p className="text-2xl font-semibold text-gray-900">{metrics.unique_assignees}</p>
              </div>
            </div>
          </div>

          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                  <Clock className="h-6 w-6 text-purple-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">Meetings with Tasks</p>
                <p className="text-2xl font-semibold text-gray-900">{metrics.total_meetings_with_tasks}</p>
              </div>
            </div>
          </div>

          <div className="card card-hover">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
                  <AlertCircle className="h-6 w-6 text-red-600" />
                </div>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500">High Priority</p>
                <p className="text-2xl font-semibold text-gray-900">{metrics.priority_distribution.high}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Meetings with Tasks */}
        <div className="lg:col-span-2">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Meetings with Action Items</h3>
              <span className="text-sm text-gray-500">{meetings.length} meetings</span>
            </div>
            
            {meetings.length === 0 ? (
              <div className="text-center py-12">
                <CheckSquare className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500 mb-2">No action items found</p>
                <p className="text-sm text-gray-400">
                  Generate MOMs for your meetings to see action items here
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {meetings.map((meeting, index) => (
                  <div key={meeting.meeting_id} 
                       className={`p-4 border rounded-lg hover:bg-gray-50 transition-colors cursor-pointer animate-slide-in ${
                         selectedMeeting?.meeting_id === meeting.meeting_id 
                           ? 'border-blue-500 bg-blue-50' 
                           : 'border-gray-200'
                       }`}
                       style={{ animationDelay: `${index * 0.05}s` }}
                       onClick={() => onSelectMeeting(meeting)}>
                    
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-medium text-gray-900 truncate mb-2">
                          {meeting.meeting_title}
                        </h4>
                        
                        <div className="flex items-center space-x-4 text-xs text-gray-500">
                          <div className="flex items-center space-x-1">
                            <CheckSquare className="h-3 w-3" />
                            <span>{meeting.total_items} action items</span>
                          </div>
                        </div>
                        
                        {/* Priority breakdown */}
                        <div className="flex items-center space-x-2 mt-2">
                          {meeting.action_items && (
                            <>
                              {meeting.action_items.filter(item => item.priority === 'high').length > 0 && (
                                <span className="text-xs px-2 py-1 bg-red-100 text-red-800 rounded-full">
                                  {meeting.action_items.filter(item => item.priority === 'high').length} High
                                </span>
                              )}
                              {meeting.action_items.filter(item => item.priority === 'medium').length > 0 && (
                                <span className="text-xs px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full">
                                  {meeting.action_items.filter(item => item.priority === 'medium').length} Medium
                                </span>
                              )}
                              {meeting.action_items.filter(item => item.priority === 'low').length > 0 && (
                                <span className="text-xs px-2 py-1 bg-green-100 text-green-800 rounded-full">
                                  {meeting.action_items.filter(item => item.priority === 'low').length} Low
                                </span>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Task Details */}
        <div className="space-y-6">
          {selectedMeeting ? (
            <>
              {/* Meeting Info */}
              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Action Items</h3>
                
                <div className="space-y-3 mb-4">
                  <div>
                    <p className="text-sm font-medium text-gray-500">Meeting</p>
                    <p className="text-sm text-gray-900">{selectedMeeting.meeting_title}</p>
                  </div>
                  
                  <div>
                    <p className="text-sm font-medium text-gray-500">Total Items</p>
                    <p className="text-sm text-gray-900">{selectedMeeting.total_items}</p>
                  </div>
                </div>

                <div className="pt-4 border-t border-gray-200 space-y-3">
                  <label className="flex items-center space-x-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300"
                      checked={assignToAll}
                      onChange={(e) => setAssignToAll(e.target.checked)}
                    />
                    <span>Assign each action item to all participants</span>
                  </label>
                  <button
                    onClick={() => assignTasks(selectedMeeting.meeting_id)}
                    disabled={assigning}
                    className="btn-primary flex items-center space-x-2 w-full justify-center"
                  >
                    {assigning ? (
                      <>
                        <LoadingSpinner size="sm" />
                        <span>Assigning...</span>
                      </>
                    ) : (
                      <>
                        <Send className="h-4 w-4" />
                        <span>Assign Tasks</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Action Items List */}
              <div className="card">
                <h4 className="text-sm font-semibold text-gray-900 mb-3">Task Details</h4>
                
                {selectedMeeting.action_items && selectedMeeting.action_items.length > 0 ? (
                  <div className="space-y-3">
                    {selectedMeeting.action_items.map((item, index) => (
                      <div key={index} className="p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-start justify-between mb-2">
                          <p className="text-sm font-medium text-gray-900 flex-1 mr-2">
                            {item.task}
                          </p>
                          <span className={`text-xs px-2 py-1 rounded-full ${getPriorityColor(item.priority)}`}>
                            {item.priority}
                          </span>
                        </div>
                        
                        <div className="space-y-1">
                          <div className="flex items-center text-xs text-gray-500">
                            <User className="h-3 w-3 mr-1" />
                            <span className="truncate">{item.assigned_to}</span>
                          </div>
                          <div className="flex items-center text-xs text-gray-500">
                            <Clock className="h-3 w-3 mr-1" />
                            <span>{formatDate(item.due_date)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-4">
                    <p className="text-sm text-gray-500">No action items available</p>
                  </div>
                )}
              </div>

              {/* Assigned Tasks (Persisted) */}
              <div className="card">
                <h4 className="text-sm font-semibold text-gray-900 mb-3">Assigned Tasks</h4>
                {loadingTasks ? (
                  <div className="flex items-center justify-center py-6">
                    <LoadingSpinner size="sm" />
                  </div>
                ) : meetingTasks.length > 0 ? (
                  <div className="space-y-3">
                    {meetingTasks.map((t) => (
                      <div key={t.id} className="p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-start justify-between mb-2">
                          <p className="text-sm font-medium text-gray-900 flex-1 mr-2">
                            {t.task}
                          </p>
                          <span className={`text-xs px-2 py-1 rounded-full ${getPriorityColor(t.priority)}`}>
                            {t.priority}
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-gray-600">
                          <div className="flex items-center">
                            <User className="h-3 w-3 mr-1" />
                            <span className="truncate">{t.assignee_name || t.assigned_to}</span>
                          </div>
                          <div className="flex items-center">
                            <Clock className="h-3 w-3 mr-1" />
                            <span>{formatDate(t.due_date || '')}</span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <span className={`px-2 py-0.5 rounded-full ${getStatusBadge(t.status)}`}>{t.status.replace('_', ' ')}</span>
                            <select
                              className="text-xs border border-gray-300 rounded px-2 py-1 bg-white"
                              value={t.status}
                              disabled={updatingTaskId === t.id}
                              onChange={(e) => updateTaskStatus(t.id, e.target.value as any)}
                            >
                              <option value="pending">pending</option>
                              <option value="in_progress">in progress</option>
                              <option value="completed">completed</option>
                              <option value="blocked">blocked</option>
                            </select>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-4">
                    <p className="text-sm text-gray-500">No assigned tasks yet</p>
                  </div>
                )}
              </div>

              {/* Assignment Result */}
              {assignmentResult && (
                <div className="card">
                  <h4 className="text-sm font-semibold text-gray-900 mb-3">Assignment Results</h4>
                  
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-gray-500">Success Rate</p>
                        <p className="font-medium text-green-600">
                          {assignmentResult.metrics.success_rate.toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-500">Total Tasks</p>
                        <p className="font-medium text-gray-900">
                          {assignmentResult.metrics.total_tasks}
                        </p>
                      </div>
                    </div>
                    
                    <div className="text-xs text-gray-500">
                      <p>Planner: {assignmentResult.metrics.planner_tasks}</p>
                      <p>Email: {assignmentResult.metrics.email_tasks}</p>
                      <p>Failed: {assignmentResult.metrics.failed_tasks}</p>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="card">
              <div className="text-center py-8">
                <Eye className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">Select a meeting to view action items</p>
              </div>
            </div>
          )}

          {/* Top Assignees */}
          {metrics && metrics.top_assignees.length > 0 && (
            <div className="card">
              <h4 className="text-sm font-semibold text-gray-900 mb-3">Top Assignees</h4>
              
              <div className="space-y-2">
                {metrics.top_assignees.slice(0, 5).map((assignee, index) => (
                  <div key={assignee.assignee} className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center">
                        <span className="text-xs font-medium text-blue-600">{index + 1}</span>
                      </div>
                      <span className="text-sm text-gray-700 truncate">{assignee.assignee}</span>
                    </div>
                    <span className="text-sm font-medium text-gray-900">{assignee.task_count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Tasks;