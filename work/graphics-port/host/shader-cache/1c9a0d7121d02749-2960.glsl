
precision highp float;

struct material
{
    vec4  ambient;
    vec4  diffuse;
    vec4  emissive;
    vec4  specular;
    float shininess;
};

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;

varying vec2 vTexCoord;
varying vec4 vColor;

uniform material u_Material;
uniform float    u_PointSize;
uniform mat4     u_transformMatrix;
uniform vec4     u_position2DImage;
uniform vec4     u_texcoord2DImage;
uniform mediump float    rotationAngle; // rotation angle in radians

vec2 rotate(vec2 point, float angle)
{
	vec2 ret;
	ret.x = cos(angle) * point.x + sin(angle) * point.y;
	ret.y = -sin(angle) * point.x + cos(angle) * point.y;
 	return ret;
}

void main(void)
{
  vec2 pos = (rotate(a_Position.xy - vec2(0.5, 0.5), rotationAngle) + vec2(0.5, 0.5)) * u_position2DImage.zw + u_position2DImage.xy;
  vTexCoord = a_TextureCoordinate * u_texcoord2DImage.zw + u_texcoord2DImage.xy;

  vColor = u_Material.diffuse;
  
  vec4 transPos = u_transformMatrix * vec4(pos, 0., 1.);
  transPos /= transPos.w;
  gl_Position = vec4(transPos.xy, a_Position.z, 1.);
}
