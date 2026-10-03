import type { components } from './schema'

type Schemas = components['schemas']
export type Status = Schemas['Status']
export type GpsStatus = Schemas['GpsStatus']
export type ChronyStatus = Schemas['ChronyStatus']
export type Satellite = Schemas['Satellite']
export type Source = Schemas['Source']
export type SourceStats = Schemas['SourceStats']
export type Client = Schemas['Client']
export type HistoryPoint = Schemas['HistoryPoint']
export type PoolHistory = Schemas['PoolHistory']
export type PoolScore = Schemas['PoolScore']
export type SystemStatus = Schemas['SystemStatus']
