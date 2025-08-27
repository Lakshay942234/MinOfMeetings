import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import { Calendar, TrendingUp, Users, IndianRupee, Filter, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useApi } from '../contexts/ApiContext';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

interface AnalyticsData {
  summary: any;
  trends: any[];
  departments: any[];
  users: any[];
  actionItems: any;
}

const Analytics: React.FC = () => {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState('30'); // days
  const [selectedDepartment, setSelectedDepartment] = useState<string>('');
  const [groupBy, setGroupBy] = useState<'day' | 'week' | 'month'>('day');
  const [prevSummary, setPrevSummary] = useState<any | null>(null);

  const api = useApi();

  useEffect(() => {
    loadAnalytics();
  }, [dateRange, selectedDepartment, groupBy]);

  const loadAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);

      const endDateObj = new Date();
      const startDateObj = new Date(Date.now() - parseInt(dateRange) * 24 * 60 * 60 * 1000);
      const endDate = endDateObj.toISOString();
      const startDate = startDateObj.toISOString();
      // Previous period (same length immediately before current start)
      const periodMs = endDateObj.getTime() - startDateObj.getTime();
      const prevEndDate = startDateObj.toISOString();
      const prevStartDate = new Date(startDateObj.getTime() - periodMs).toISOString();

      // Load all analytics data
      const [summaryRes, prevSummaryRes, trendsRes, departmentRes, usersRes, actionItemsRes] = await Promise.all([
        api.get(`/analytics/summary?start_date=${startDate}&end_date=${endDate}`),
        api.get(`/analytics/summary?start_date=${prevStartDate}&end_date=${prevEndDate}`),
        api.get(`/analytics/trends?start_date=${startDate}&end_date=${endDate}&group_by=${groupBy}`),
        api.get(`/analytics/department-analytics?start_date=${startDate}&end_date=${endDate}`),
        api.get(`/analytics/meetings-per-user?start_date=${startDate}&end_date=${endDate}${selectedDepartment ? `&department=${selectedDepartment}` : ''}`),
        api.get(`/analytics/action-items?start_date=${startDate}&end_date=${endDate}`)
      ]);

      setData({
        summary: summaryRes.summary,
        trends: trendsRes.trends,
        departments: departmentRes.departments,
        users: usersRes.users,
        actionItems: actionItemsRes.action_items
      });
      setPrevSummary(prevSummaryRes.summary);

    } catch (error) {
      console.error('Error loading analytics:', error);
      setError(`Failed to load analytics: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
    }).format(amount);
  };

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d'];

  const percentDelta = (current?: number, previous?: number) => {
    if (previous === undefined || previous === null) return 0;
    if (!previous) return 0;
    const delta = ((Number(current || 0) - Number(previous)) / Number(previous)) * 100;
    return delta;
  };

  const DeltaBadge: React.FC<{ current?: number; previous?: number }> = ({ current, previous }) => {
    if (previous === undefined || previous === null) return null;
    const d = percentDelta(current, previous);
    const up = d >= 0;
    return (
      <span className={`inline-flex items-center text-xs ${up ? 'text-green-600' : 'text-red-600'}`}>
        {up ? <ArrowUpRight className="h-3 w-3 mr-0.5" /> : <ArrowDownRight className="h-3 w-3 mr-0.5" />}
        {Math.abs(d).toFixed(0)}%
      </span>
    );
  };

  const priorityChartData = data
    ? Object.entries(data.actionItems?.priority_distribution || {}).map(([name, value]) => ({ name, value: value as number }))
    : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-gray-600">Loading analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-gray-600">Meeting insights and productivity metrics</p>
        </div>

        {/* Filters */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <Filter className="h-4 w-4 text-gray-500" />
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="form-input text-sm"
            >
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </select>
          </div>

          <div>
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as 'day' | 'week' | 'month')}
              className="form-input text-sm"
            >
              <option value="day">Group by day</option>
              <option value="week">Group by week</option>
              <option value="month">Group by month</option>
            </select>
          </div>

          {data && data.departments.length > 0 && (
            <select
              value={selectedDepartment}
              onChange={(e) => setSelectedDepartment(e.target.value)}
              className="form-input text-sm"
            >
              <option value="">All Departments</option>
              {data.departments.map((dept) => (
                <option key={dept.department} value={dept.department}>
                  {dept.department}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {error && (
        <ErrorAlert message={error} onClose={() => setError(null)} />
      )}

      {data && (
        <>
          {/* Summary Cards */}
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
                  <p className="text-2xl font-semibold text-gray-900">{data.summary.total_meetings}</p>
                  <div className="flex items-center space-x-2">
                    <p className="text-xs text-gray-400">Last {dateRange} days</p>
                    {prevSummary && (
                      <DeltaBadge current={data.summary.total_meetings} previous={prevSummary.total_meetings} />
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="card card-hover">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                    <TrendingUp className="h-6 w-6 text-green-600" />
                  </div>
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Meeting Hours</p>
                  <p className="text-2xl font-semibold text-gray-900">{data.summary.total_hours}</p>
                  <div className="flex items-center space-x-2">
                    <p className="text-xs text-gray-400">Avg {data.summary.avg_duration_minutes}min per meeting</p>
                    {prevSummary && (
                      <DeltaBadge current={data.summary.total_hours} previous={prevSummary.total_hours} />
                    )}
                  </div>
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
                  <p className="text-2xl font-semibold text-gray-900">{formatCurrency(data.summary.total_cost)}</p>
                  <div className="flex items-center space-x-2">
                    <p className="text-xs text-gray-400">Based on estimated salaries</p>
                    {prevSummary && (
                      <DeltaBadge current={data.summary.total_cost} previous={prevSummary.total_cost} />
                    )}
                  </div>
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
                  <p className="text-sm font-medium text-gray-500">Participants</p>
                  <p className="text-2xl font-semibold text-gray-900">{data.summary.unique_participants}</p>
                  <div className="flex items-center space-x-2">
                    <p className="text-xs text-gray-400">Avg {data.summary.avg_participants} per meeting</p>
                    {prevSummary && (
                      <DeltaBadge current={data.summary.unique_participants} previous={prevSummary.unique_participants} />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Meeting Trends */}
            <div className="chart-container">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Meeting Trends</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data.trends}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="period" 
                    tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => formatCurrency(v as number)} />
                  <Tooltip 
                    labelFormatter={(value) => new Date(value).toLocaleDateString()}
                    formatter={(value, name) => [
                      name === 'meeting_count' ? value : 
                      name === 'total_cost' ? formatCurrency(value as number) : 
                      `${value}h`,
                      name === 'meeting_count' ? 'Meetings' :
                      name === 'total_cost' ? 'Cost' : 'Hours'
                    ]}
                  />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="meeting_count" stroke="#0088FE" name="Meetings" strokeWidth={2} />
                  <Line yAxisId="left" type="monotone" dataKey="total_hours" stroke="#00C49F" name="Hours" strokeWidth={2} />
                  <Line yAxisId="right" type="monotone" dataKey="total_cost" stroke="#FF8042" name="Cost" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Department Costs */}
            <div className="chart-container">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Department Analysis</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={data.departments.slice(0, 5)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="department" />
                  <YAxis tickFormatter={(value) => formatCurrency(value as number)} />
                  <Tooltip formatter={(value) => [formatCurrency(value as number), 'Meeting Cost']} />
                  <Bar dataKey="total_cost" fill="#0088FE" />
                </BarChart>
              </ResponsiveContainer>
              {/* Department metrics table */}
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500">
                      <th className="py-2 pr-4">Department</th>
                      <th className="py-2 pr-4">Meetings</th>
                      <th className="py-2 pr-4">Hours</th>
                      <th className="py-2 pr-4">Avg Participants</th>
                      <th className="py-2 pr-4">Avg Duration (min)</th>
                      <th className="py-2 pr-4">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.departments.slice(0, 8).map((dept) => (
                      <tr key={dept.department} className="border-t border-gray-100">
                        <td className="py-2 pr-4 text-gray-900">{dept.department}</td>
                        <td className="py-2 pr-4">{dept.meeting_count}</td>
                        <td className="py-2 pr-4">{dept.total_hours}</td>
                        <td className="py-2 pr-4">{dept.avg_participants}</td>
                        <td className="py-2 pr-4">{dept.avg_duration_minutes}</td>
                        <td className="py-2 pr-4">{formatCurrency(dept.total_cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top Users */}
            <div className="card">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Most Active Participants</h3>
              <div className="space-y-4">
                {data.users.slice(0, 8).map((user, index) => (
                  <div key={user.email} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                        <span className="text-xs font-medium text-blue-600">{index + 1}</span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{user.display_name}</p>
                        <p className="text-xs text-gray-500">{user.email}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-gray-900">{user.meeting_count} meetings</p>
                      <p className="text-xs text-gray-500">{user.total_hours}h total • {formatCurrency(user.total_cost)}</p>
                      <p className="text-xs text-gray-400">Avg {(user.total_minutes && user.meeting_count) ? Math.round(user.total_minutes / user.meeting_count) : 0} min/meeting</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Action Items Analysis */}
            <div className="card">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Action Items Overview</h3>
              
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="text-center">
                  <p className="text-2xl font-bold text-blue-600">{data.actionItems.total_action_items}</p>
                  <p className="text-sm text-gray-600">Total Action Items</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-green-600">{data.actionItems.meetings_with_action_items}</p>
                  <p className="text-sm text-gray-600">Meetings with Tasks</p>
                </div>
              </div>

              {/* Priority Distribution */}
              <div className="mb-4 grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-2">Priority Distribution</h4>
                  <div className="space-y-2">
                    {Object.entries(data.actionItems.priority_distribution).map(([priority, count]) => (
                      <div key={priority} className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <div className={`w-3 h-3 rounded-full ${
                            priority === 'high' ? 'bg-red-500' :
                            priority === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                          }`} />
                          <span className="text-sm capitalize text-gray-600">{priority}</span>
                        </div>
                        <span className="text-sm font-medium text-gray-900">{count as number}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={priorityChartData} dataKey="value" nameKey="name" outerRadius={60} label>
                        {priorityChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={
                            entry.name === 'high' ? '#ef4444' : entry.name === 'medium' ? '#f59e0b' : '#10b981'
                          } />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v: number, n: string) => [v, n]} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Top Assignees */}
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-2">Top Assignees</h4>
                <div className="space-y-1">
                  {data.actionItems.top_assignees.slice(0, 5).map(([assignee, count]: [string, number]) => (
                    <div key={assignee} className="flex items-center justify-between text-sm">
                      <span className="text-gray-600 truncate">{assignee}</span>
                      <span className="font-medium text-gray-900">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Analytics;