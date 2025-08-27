import React, { createContext, useContext, ReactNode } from 'react';
import { useAuth } from './AuthContext';

interface ApiContextType {
  get: (endpoint: string) => Promise<any>;
  post: (endpoint: string, data?: any) => Promise<any>;
  put: (endpoint: string, data?: any) => Promise<any>;
  delete: (endpoint: string) => Promise<any>;
}

const ApiContext = createContext<ApiContextType | undefined>(undefined);

export const useApi = () => {
  const context = useContext(ApiContext);
  if (context === undefined) {
    throw new Error('useApi must be used within an ApiProvider');
  }
  return context;
};

interface ApiProviderProps {
  children: ReactNode;
}

export const ApiProvider: React.FC<ApiProviderProps> = ({ children }) => {
  const { user, logout } = useAuth();
  
  const baseURL = 'http://localhost:8000/api';

  const makeRequest = async (endpoint: string, options: RequestInit = {}) => {
    const url = `${baseURL}${endpoint}`;
    
    const defaultHeaders = {
      'Content-Type': 'application/json',
    };

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);
      
      if (response.status === 401) {
        logout();
        throw new Error('Authentication required');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json().catch(() => ({}));
      return data;
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  };

  const get = async (endpoint: string) => {
    return makeRequest(endpoint, { method: 'GET' });
  };

  const post = async (endpoint: string, data?: any) => {
    return makeRequest(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  };

  const put = async (endpoint: string, data?: any) => {
    return makeRequest(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  };

  const del = async (endpoint: string) => {
    return makeRequest(endpoint, { method: 'DELETE' });
  };

  const value = {
    get,
    post,
    put,
    delete: del,
  };

  return (
    <ApiContext.Provider value={value}>
      {children}
    </ApiContext.Provider>
  );
};