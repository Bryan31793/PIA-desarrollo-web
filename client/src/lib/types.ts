export type Role = 'admin' | 'staff' | 'member';
export interface Identity {
  subject: string;
  role: Role;
}
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}
export interface Session {
  tokens: TokenPair;
  identity: Identity;
  email: string;
}
export interface MemberInput {
  name: string;
  email: string;
  password: string;
}
export interface Member {
  member_id: number;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}
export interface EmployeeInput extends MemberInput {
  role: 'admin' | 'staff';
}
export interface Employee {
  employee_id: number;
  name: string;
  email: string;
  role: 'admin' | 'staff';
  is_active: boolean;
  created_at: string;
}
export interface PlanInput {
  name: string;
  price: string;
  duration_days: number;
}
export interface Plan extends PlanInput {
  plan_id: number;
}
export interface CurrentMembership {
  membership_id: number;
  plan_id: number;
  plan_name: string;
  start_date: string;
  end_date: string;
}
export interface MembershipStatus {
  has_active_plan: boolean;
  membership: CurrentMembership | null;
}
export interface Payment {
  payment_id: number;
  membership_id: number;
  employee_id: number;
  amount: string;
  currency: string;
  paid_at: string;
  notes: string | null;
}
export interface Membership {
  membership_id: number;
  member_id: number;
  plan_id: number;
  start_date: string;
  end_date: string;
  payment: Payment;
}
export interface AccessPass {
  pass_token: string;
  expires_at: string;
  expires_in: number;
}
export interface CheckIn {
  check_in_id: number;
  member_id: number;
  member_name: string;
  membership_id: number;
  employee_id: number;
  checked_in_at: string;
}
