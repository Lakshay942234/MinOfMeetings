import React, { useState } from 'react';
import { Plus, X, Edit2, Check } from 'lucide-react';

interface EditableListProps {
  title: string;
  items: string[];
  onUpdate: (items: string[]) => void;
  placeholder?: string;
}

const EditableList: React.FC<EditableListProps> = ({ 
  title, 
  items, 
  onUpdate, 
  placeholder = "Add new item..." 
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editItems, setEditItems] = useState<string[]>(items);
  const [newItem, setNewItem] = useState('');

  const handleStartEdit = () => {
    setEditItems([...items]);
    setIsEditing(true);
  };

  const handleSave = () => {
    onUpdate(editItems.filter(item => item.trim() !== ''));
    setIsEditing(false);
    setNewItem('');
  };

  const handleCancel = () => {
    setEditItems([...items]);
    setIsEditing(false);
    setNewItem('');
  };

  const handleAddItem = () => {
    if (newItem.trim()) {
      setEditItems([...editItems, newItem.trim()]);
      setNewItem('');
    }
  };

  const handleRemoveItem = (index: number) => {
    setEditItems(editItems.filter((_, i) => i !== index));
  };

  const handleUpdateItem = (index: number, value: string) => {
    const updated = [...editItems];
    updated[index] = value;
    setEditItems(updated);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium text-gray-900">{title}</h4>
        {!isEditing && items.length > 0 && (
          <button
            onClick={handleStartEdit}
            className="text-blue-600 hover:text-blue-700 p-1"
            title="Edit"
          >
            <Edit2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {!isEditing ? (
        items.length > 0 ? (
          <ul className="list-disc list-inside space-y-1 text-gray-700">
            {items.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        ) : (
          <div className="text-center py-4">
            <p className="text-gray-500 text-sm mb-2">No {title.toLowerCase()} added yet</p>
            <button
              onClick={handleStartEdit}
              className="btn-secondary text-sm"
            >
              <Plus className="h-4 w-4 mr-1" />
              Add {title.slice(0, -1)}
            </button>
          </div>
        )
      ) : (
        <div className="space-y-3">
          {editItems.map((item, index) => (
            <div key={index} className="flex items-center space-x-2">
              <input
                type="text"
                value={item}
                onChange={(e) => handleUpdateItem(index, e.target.value)}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => handleRemoveItem(index)}
                className="text-red-600 hover:text-red-700 p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
          
          <div className="flex items-center space-x-2">
            <input
              type="text"
              value={newItem}
              onChange={(e) => setNewItem(e.target.value)}
              placeholder={placeholder}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              onKeyPress={(e) => e.key === 'Enter' && handleAddItem()}
            />
            <button
              onClick={handleAddItem}
              disabled={!newItem.trim()}
              className="text-blue-600 hover:text-blue-700 disabled:text-gray-400 p-1"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          
          <div className="flex items-center space-x-2 pt-2">
            <button
              onClick={handleSave}
              className="btn-primary text-sm flex items-center space-x-1"
            >
              <Check className="h-4 w-4" />
              <span>Save</span>
            </button>
            <button
              onClick={handleCancel}
              className="btn-secondary text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default EditableList;
