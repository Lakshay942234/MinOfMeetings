import React, { useState, useEffect } from 'react';
import { Calendar, Clock, Users, FileText, Play, Eye, Download, Edit3, Save, X } from 'lucide-react';
import { useApi } from '../contexts/ApiContext';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';
import EditableList from '../components/EditableList';
import ActionItemEditor from '../components/ActionItemEditor';

interface Meeting {
  meeting_id: string;
  title: string;
  date: string;
  duration_minutes: number;
  participants_count: number;
  has_mom: boolean;
  has_transcript: boolean;
  transcript_text?: string;
  transcription_status?: string;
  transcription_method?: string;
  mom_generated?: boolean;
}

interface ActionItem {
  id?: string;
  task: string;
  assigned_to: string;
  due_date?: string;
  priority: 'low' | 'medium' | 'high';
  status: 'pending' | 'in_progress' | 'completed' | 'blocked';
  description?: string;
}

interface MOM {
  id?: number;
  meeting_id: string;
  meeting_title: string;
  date: string;
  agenda: Array<{ text: string } | string>;
  key_decisions: Array<{ text: string } | string>;
  action_items: ActionItem[];
  follow_up_points: Array<{ text: string } | string>;
  created_at?: string;
}

const Meetings: React.FC = () => {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const [meetingDetails, setMeetingDetails] = useState<any>(null);
  const [mom, setMom] = useState<MOM | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingMom, setGeneratingMom] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [isEditingMom, setIsEditingMom] = useState(false);
  const [editTitle, setEditTitle] = useState('');

  const api = useApi();

  useEffect(() => {
    loadMeetings();
  }, []);

  const loadMeetings = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await api.get('/meetings?limit=50');
      setMeetings(response.meetings || []);
    } catch (error) {
      console.error('Error loading meetings:', error);
      setError(`Failed to load meetings: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const loadMeetingDetails = async (meetingId: string) => {
    try {
      const response = await api.get(`/meetings/${meetingId}`);
      setMeetingDetails(response);
      
      if (response.mom) {
        setMom(response.mom);
        setEditTitle(response.mom.meeting_title || '');
      } else {
        setMom(null);
        setEditTitle('');
      }
      
      setShowDetails(true);
    } catch (error) {
      console.error('Error loading meeting details:', error);
      setError(`Failed to load meeting details: ${error}`);
    }
  };

  const generateMOM = async (meetingId: string) => {
    try {
      setGeneratingMom(true);
      setError(null);
      
      const response = await api.post(`/meetings/generate-mom/${meetingId}`);
      setMom(response.mom);
      
      // Update the meeting in the list
      setMeetings(meetings.map(m => 
        m.meeting_id === meetingId 
          ? { ...m, has_mom: true }
          : m
      ));
      
    } catch (error) {
      console.error('Error generating MOM:', error);
      setError(`Failed to generate MOM: ${error}`);
    } finally {
      setGeneratingMom(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Ensure backend-friendly datetime string or null
  const toBackendDateTime = (dateStr?: string | null) => {
    if (!dateStr) return null;
    if (dateStr.includes('T')) return dateStr;
    // Expecting YYYY-MM-DD from <input type="date">
    return `${dateStr}T00:00:00`;
  };

  // API functions for editing MOM and action items
  const updateMOM = async (meetingId: string, updates: Partial<MOM>) => {
    try {
      console.log('Updating MOM for meeting:', meetingId, 'with updates:', updates);
      const response = await api.put(`/mom/mom/${meetingId}`, updates);
      console.log('MOM update response:', response);
      if (mom) {
        setMom({ ...mom, ...updates });
      }
      setError(null);
    } catch (error) {
      console.error('Error updating MOM:', error);
      setError(`Failed to update MOM: ${error}`);
    }
  };

  const addActionItem = async (meetingId: string, item: Omit<ActionItem, 'id'>) => {
    try {
      console.log('Adding action item for meeting:', meetingId, 'item:', item);
      const payload = { ...item, due_date: toBackendDateTime(item.due_date || undefined) };
      const response = await api.post(`/mom/action-items/${meetingId}`, payload);
      console.log('Add action item response:', response);
      if (mom) {
        setMom({
          ...mom,
          action_items: [...mom.action_items, response]
        });
      }
      setError(null);
    } catch (error) {
      console.error('Error adding action item:', error);
      setError(`Failed to add action item: ${error}`);
    }
  };

  const updateActionItems = async (items: ActionItem[]) => {
    try {
      console.log('Updating action items:', items);
      // Update each item individually via API
      for (const item of items) {
        if (item.id) {
          console.log('Updating action item:', item.id, item);
          await api.put(`/mom/action-items/${item.id}`, {
            task: item.task,
            assigned_to: item.assigned_to,
            due_date: toBackendDateTime(item.due_date || undefined),
            priority: item.priority,
            status: item.status,
            description: item.description
          });
        }
      }
      // Update local state
      if (mom) {
        setMom({ ...mom, action_items: items });
      }
      setError(null);
      console.log('Action items updated successfully');
    } catch (error) {
      console.error('Error updating action items:', error);
      setError(`Failed to update action items: ${error}`);
    }
  };

  const deleteActionItem = async (id: string) => {
    try {
      console.log('Deleting action item:', id);
      await api.delete(`/mom/action-items/${id}`);
      if (mom) {
        setMom({
          ...mom,
          action_items: mom.action_items.filter(item => item.id !== id)
        });
      }
      setError(null);
      console.log('Action item deleted successfully');
    } catch (error) {
      console.error('Error deleting action item:', error);
      setError(`Failed to delete action item: ${error}`);
    }
  };

  const updateActionItemStatus = async (id: string, status: ActionItem['status']) => {
    try {
      await api.put(`/mom/action-items/${id}/status?status=${encodeURIComponent(status)}`);
      if (mom) {
        setMom({
          ...mom,
          action_items: mom.action_items.map(item => 
            item.id === id ? { ...item, status } : item
          )
        });
      }
      setError(null);
    } catch (error) {
      console.error('Error updating action item status:', error);
      setError(`Failed to update status: ${error}`);
    }
  };

  const handleSaveMomTitle = async () => {
    if (selectedMeeting && editTitle.trim()) {
      await updateMOM(selectedMeeting.meeting_id, { meeting_title: editTitle.trim() });
      setIsEditingMom(false);
    }
  };

  const exportMOM = (mom: MOM) => {
    const content = `
# Minutes of Meeting

**Meeting:** ${mom.meeting_title}
**Date:** ${formatDate(mom.date)}

## Agenda
${mom.agenda.map(item => `- ${item}`).join('\n')}

## Key Decisions
${mom.key_decisions.map(item => `- ${item}`).join('\n')}

## Action Items
${mom.action_items.map(item => 
  `- **Task:** ${item.task}\n  **Assigned to:** ${item.assigned_to}\n  **Due:** ${item.due_date || 'Not specified'}\n  **Priority:** ${item.priority || 'Medium'}`
).join('\n\n')}

## Follow-up Points
${mom.follow_up_points.map(item => `- ${item}`).join('\n')}
    `.trim();

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${mom.meeting_title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_mom.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-gray-600">Loading meetings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Meetings</h1>
          <p className="text-gray-600">Manage your Teams meetings and generate MOMs</p>
        </div>
      </div>

      {error && (
        <ErrorAlert message={error} onClose={() => setError(null)} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Meetings List */}
        <div className="lg:col-span-2">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Recent Meetings</h3>
              <span className="text-sm text-gray-500">{meetings.length} meetings</span>
            </div>
            
            {meetings.length === 0 ? (
              <div className="text-center py-12">
                <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500 mb-2">No meetings found</p>
                <p className="text-sm text-gray-400">
                  Sync your Teams meetings from the Dashboard to get started
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
                       onClick={() => {
                         setSelectedMeeting(meeting);
                         loadMeetingDetails(meeting.meeting_id);
                       }}>
                    
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-medium text-gray-900 truncate mb-2">
                          {meeting.title}
                        </h4>
                        
                        <div className="flex items-center space-x-4 text-xs text-gray-500">
                          <div className="flex items-center space-x-1">
                            <Calendar className="h-3 w-3" />
                            <span>{formatDate(meeting.date)}</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <Clock className="h-3 w-3" />
                            <span>{meeting.duration_minutes}min</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <Users className="h-3 w-3" />
                            <span>{meeting.participants_count}</span>
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
                            return <span className="status-secondary">Scheduled</span>;
                          }
                          
                          // Meeting happened, check status
                          if (hasMOM) {
                            return <span className="status-success">MOM Generated</span>;
                          } else if (hasTranscript) {
                            return <span className="status-info">Generate MOM</span>;
                          } else {
                            return <span className="status-warning">Waiting</span>;
                          }
                        })()} 
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Meeting Details */}
        <div className="space-y-6">
          {selectedMeeting ? (
            <>
              {/* Meeting Info */}
              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Meeting Details</h3>
                
                <div className="space-y-3">
                  <div>
                    <p className="text-sm font-medium text-gray-500">Title</p>
                    <p className="text-sm text-gray-900">{selectedMeeting.title}</p>
                  </div>
                  
                  <div>
                    <p className="text-sm font-medium text-gray-500">Date & Time</p>
                    <p className="text-sm text-gray-900">{formatDate(selectedMeeting.date)}</p>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm font-medium text-gray-500">Duration</p>
                      <p className="text-sm text-gray-900">{selectedMeeting.duration_minutes} minutes</p>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-500">Participants</p>
                      <p className="text-sm text-gray-900">{selectedMeeting.participants_count}</p>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-gray-200">
                  <button
                    onClick={() => setShowDetails(!showDetails)}
                    className="btn-secondary flex items-center space-x-2 w-full justify-center"
                  >
                    <Eye className="h-4 w-4" />
                    <span>{showDetails ? 'Hide' : 'Show'} Details</span>
                  </button>
                </div>

                {showDetails && meetingDetails && Array.isArray(meetingDetails.participants) && (
                  <div className="mt-4 space-y-3">
                    <h4 className="text-sm font-medium text-gray-900">Participants</h4>
                    {meetingDetails.participants.length === 0 ? (
                      <p className="text-sm text-gray-500">No participants found</p>
                    ) : (
                      <ul className="divide-y divide-gray-200 rounded border">
                        {meetingDetails.participants.map((p: any, idx: number) => (
                          <li key={idx} className="p-2 text-sm flex items-center justify-between">
                            <div className="flex flex-col">
                              <span className="text-gray-900 font-medium">{p.name || p.email || 'Unknown'}</span>
                              <span className="text-gray-500">{p.email || ''}</span>
                            </div>
                            {p.type && (
                              <span className="text-xs text-gray-500 capitalize">{p.type}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Actions</h3>
                
                <div className="space-y-3">
                  {!selectedMeeting.has_mom ? (
                    <button
                      onClick={() => generateMOM(selectedMeeting.meeting_id)}
                      disabled={generatingMom}
                      className="btn-primary flex items-center space-x-2 w-full justify-center"
                    >
                      {generatingMom ? (
                        <>
                          <LoadingSpinner size="sm" />
                          <span>Generating...</span>
                        </>
                      ) : (
                        <>
                          <Play className="h-4 w-4" />
                          <span>Generate MOM</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <div className="text-center py-2">
                      <span className="status-success">MOM Generated</span>
                    </div>
                  )}
                  
                  {mom && (
                    <button
                      onClick={() => exportMOM(mom)}
                      className="btn-secondary flex items-center space-x-2 w-full justify-center"
                    >
                      <Download className="h-4 w-4" />
                      <span>Export MOM</span>
                    </button>
                  )}
                </div>
              </div>

              {/* MOM Display */}
              {mom && (
                <div className="card">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-2 flex-1">
                      {isEditingMom ? (
                        <div className="flex items-center space-x-2 flex-1">
                          <input
                            type="text"
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            className="flex-1 px-3 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="Meeting title..."
                          />
                          <button
                            onClick={handleSaveMomTitle}
                            className="text-green-600 hover:text-green-700 p-1"
                            title="Save title"
                          >
                            <Save className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              setIsEditingMom(false);
                              setEditTitle(mom.meeting_title);
                            }}
                            className="text-gray-600 hover:text-gray-700 p-1"
                            title="Cancel"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <h3 className="text-lg font-semibold text-gray-900">Minutes of Meeting</h3>
                          <button
                            onClick={() => setIsEditingMom(true)}
                            className="text-blue-600 hover:text-blue-700 p-1"
                            title="Edit meeting title"
                          >
                            <Edit3 className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  
                  <div className="space-y-6 text-sm">
                    {/* Meeting Title Display */}
                    {!isEditingMom && (
                      <div>
                        <h4 className="font-medium text-gray-900 mb-2">Meeting Title</h4>
                        <p className="text-gray-700">{mom.meeting_title}</p>
                      </div>
                    )}
                    
                    {/* Editable Agenda */}
                    <EditableList
                      title="Agenda"
                      items={mom.agenda?.map(item => typeof item === 'string' ? item : (item as any)?.text || (item as any)?.content || '') || []}
                      onUpdate={(items) => selectedMeeting && updateMOM(selectedMeeting.meeting_id, { agenda: items.map(item => ({ text: item })) })}
                      placeholder="Add agenda item..."
                    />
                    
                    {/* Editable Key Decisions */}
                    <EditableList
                      title="Key Decisions"
                      items={mom.key_decisions?.map(item => typeof item === 'string' ? item : (item as any)?.text || (item as any)?.content || '') || []}
                      onUpdate={(items) => selectedMeeting && updateMOM(selectedMeeting.meeting_id, { key_decisions: items.map(item => ({ text: item })) })}
                      placeholder="Add decision..."
                    />
                    
                    {/* Editable Follow-up Points */}
                    <EditableList
                      title="Follow-up Points"
                      items={mom.follow_up_points?.map(item => typeof item === 'string' ? item : (item as any)?.text || (item as any)?.content || '') || []}
                      onUpdate={(items) => selectedMeeting && updateMOM(selectedMeeting.meeting_id, { follow_up_points: items.map(item => ({ text: item })) })}
                      placeholder="Add follow-up point..."
                    />
                    
                    {/* Action Items Editor */}
                    <ActionItemEditor
                      actionItems={mom.action_items}
                      onUpdate={updateActionItems}
                      onAdd={(item) => selectedMeeting && addActionItem(selectedMeeting.meeting_id, item)}
                      onDelete={deleteActionItem}
                      onStatusUpdate={updateActionItemStatus}
                    />
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="card">
              <div className="text-center py-8">
                <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">Select a meeting to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Meetings;