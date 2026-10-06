// Package contract preserves Backend imports while sharing the wire contract with JC.
package contract

import c "gpu-ops-advisor/shared/contract"

type Object = c.Object
type Scope = c.Scope
type ClusterScope = c.ClusterScope
type Problem = c.Problem

var Fail = c.Fail
var Invalid = c.Invalid
var ID = c.ID
var Hash = c.Hash
var String = c.String
var Number = c.Number
var Has = c.Has
var ParseScope = c.ParseScope
var Contains = c.Contains
var TimeRange = c.TimeRange

func Decode[T any](v any) (T, error) { return c.Decode[T](v) }

var ValidateTopicGroups = c.ValidateTopicGroups
var ReportTopicGroups = c.ReportTopicGroups
