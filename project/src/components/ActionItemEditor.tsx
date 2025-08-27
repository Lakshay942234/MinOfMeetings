import React, { useState } from 'react';
import { Plus, X, Edit2, Check, Trash2, User, Calendar, AlertTriangle } from 'lucide-react';

interface ActionItem {
  id?: string;
  task: string;
  assigned_to: string;
  due_date?: string;
  priority: 'low' | 'medium' | 'high';
  status: 'pending' | 'in_progress' | 'completed' | 'blocked';
  description?: string;
}

interface ActionItemEditorProps {
  actionItems: ActionItem[];
  onUpdate: (items: ActionItem[]) => void;
  onAdd: (item: Omit<ActionItem, 'id'>) => void;
  onDelete: (id: string) => void;
  onStatusUpdate: (id: string, status: ActionItem['status']) => void;
}

const ActionItemEditor: React.FC<ActionItemEditorProps> = ({
  actionItems,
  onUpdate,
  onAdd,
  onDelete,
  onStatusUpdate
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editingItem, setEditingItem] = useState<ActionItem | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newItem, setNewItem] = useState<Omit<ActionItem, 'id'>>({
    task: '',
    assigned_to: '',
    due_date: '',
    priority: 'medium',
    status: 'pending',
    description: ''
  });

  const priorityColors = {
    low: 'bg-green-100 text-green-800',
    medium: 'bg-yellow-100 text-yellow-800',
    high: 'bg-red-100 text-red-800'
  };

  const statusColors = {
    pending: 'bg-gray-100 text-gray-800',
    in_progress: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    blocked: 'bg-red-100 text-red-800'
  };

  const handleAddItem = async () => {
    if (newItem.task.trim() && newItem.assigned_to.trim()) {
      await onAdd(newItem);
      setNewItem({
        task: '',
        assigned_to: '',
        due_date: '',
        priority: 'medium',
        status: 'pending',
        description: ''
      });
      setShowAddForm(false);
    }
  };

  const handleEditItem = (item: ActionItem) => {
    setEditingItem({ ...item });
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (editingItem && editingItem.id) {
      const updatedItems = actionItems.map(item => 
        item.id === editingItem.id ? editingItem : item
      );
      await onUpdate(updatedItems);
      setEditingItem(null);
      setIsEditing(false);
    }
  };

  const handleStatusChange = async (id: string, status: ActionItem['status']) => {
    await onStatusUpdate(id, status);
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'No due date';
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h4 className="font-medium text-gray-900">Action Items</h4>
        <button
          onClick={() => setShowAddForm(true)}
          className="btn-primary text-sm flex items-center space-x-1"
        >
          <Plus className="h-4 w-4" />
          <span>Add Item</span>
        </button>
      </div>

      {/* Add New Item Form */}
      {showAddForm && (
        <div className="mb-4 p-4 bg-gray-50 rounded-lg border">
          <h5 className="font-medium text-gray-900 mb-3">Add New Action Item</h5>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Task</label>
              <input
                type="text"
                value={newItem.task}
                onChange={(e) => setNewItem({ ...newItem, task: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Enter task description..."
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Assigned To</label>
                <input
                  type="email"
                  value={newItem.assigned_to}
                  onChange={(e) => setNewItem({ ...newItem, assigned_to: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="user@company.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Due Date</label>
                <input
                  type="date"
                  value={newItem.due_date}
                  onChange={(e) => setNewItem({ ...newItem, due_date: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Priority</label>
                <select
                  value={newItem.priority}
                  onChange={(e) => setNewItem({ ...newItem, priority: e.target.value as ActionItem['priority'] })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <select
                  value={newItem.status}
                  onChange={(e) => setNewItem({ ...newItem, status: e.target.value as ActionItem['status'] })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="pending">Pending</option>
                  <option value="in_progress">In Progress</option>
                  <option value="completed">Completed</option>
                  <option value="blocked">Blocked</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description (Optional)</label>
              <textarea
                value={newItem.description}
                onChange={(e) => setNewItem({ ...newItem, description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                rows={2}
                placeholder="Additional details..."
              />
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={handleAddItem}
                disabled={!newItem.task.trim() || !newItem.assigned_to.trim()}
                className="btn-primary text-sm flex items-center space-x-1"
              >
                <Check className="h-4 w-4" />
                <span>Add Item</span>
              </button>
              <button
                onClick={() => setShowAddForm(false)}
                className="btn-secondary text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Items List */}
      {actionItems.length === 0 ? (
        <div className="text-center py-8">
          <AlertTriangle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-500">No action items yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {actionItems.map((item, index) => (
            <div key={item.id || index} className="p-4 bg-white border rounded-lg">
              {isEditing && editingItem?.id === item.id ? (
                // Edit Form
                <div className="space-y-3">
                  <input
                    type="text"
                    value={editingItem.task}
                    onChange={(e) => setEditingItem({ ...editingItem, task: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="email"
                      value={editingItem.assigned_to}
                      onChange={(e) => setEditingItem({ ...editingItem, assigned_to: e.target.value })}
                      className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <input
                      type="date"
                      value={editingItem.due_date || ''}
                      onChange={(e) => setEditingItem({ ...editingItem, due_date: e.target.value })}
                      className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={handleSaveEdit}
                      className="btn-primary text-sm flex items-center space-x-1"
                    >
                      <Check className="h-4 w-4" />
                      <span>Save</span>
                    </button>
                    <button
                      onClick={() => setIsEditing(false)}
                      className="btn-secondary text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                // Display Mode
                <div>
                  <div className="flex items-start justify-between mb-2">
                    <h5 className="font-medium text-gray-900 flex-1">{item.task}</h5>
                    <div className="flex items-center space-x-2 ml-4">
                      <button
                        onClick={() => handleEditItem(item)}
                        className="text-blue-600 hover:text-blue-700 p-1"
                        title="Edit"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      {item.id && (
                        <button
                          onClick={() => onDelete(item.id!)}
                          className="text-red-600 hover:text-red-700 p-1"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-4 text-sm text-gray-600 mb-2">
                    <div className="flex items-center space-x-1">
                      <User className="h-4 w-4" />
                      <span>{item.assigned_to}</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Calendar className="h-4 w-4" />
                      <span>{formatDate(item.due_date)}</span>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${priorityColors[item.priority]}`}>
                        {item.priority.charAt(0).toUpperCase() + item.priority.slice(1)}
                      </span>
                      <select
                        value={item.status}
                        onChange={(e) => item.id && handleStatusChange(item.id, e.target.value as ActionItem['status'])}
                        className={`px-2 py-1 rounded-full text-xs font-medium border-0 focus:ring-2 focus:ring-blue-500 ${statusColors[item.status]}`}
                      >
                        <option value="pending">Pending</option>
                        <option value="in_progress">In Progress</option>
                        <option value="completed">Completed</option>
                        <option value="blocked">Blocked</option>
                      </select>
                    </div>
                  </div>
                  
                  {item.description && (
                    <p className="text-sm text-gray-600 mt-2">{item.description}</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ActionItemEditor;
