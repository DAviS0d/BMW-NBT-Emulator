precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex2;

varying highp vec3 _reflectDir;
varying mediump vec2 _varCoord;
varying highp vec3 _viewDirection;

varying highp vec3 _normal;
varying highp vec3 _tangent;
varying highp vec3 _binormal;

varying mediump float _vertexColor;

uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
uniform mediump float oparam4;



float saturate(float x)
{
	return clamp(x, 0., 1.);
}


void main()
{
	vec4 ambientColor = vec4(0.1, 0.1, 0.1, 0.);
	vec4 diffuseColor  = vec4(0.1,0.1,0.1, 0.1);
	vec4 diffuseColor2 = vec4(0.0,0.0,0.0, 0.);
	vec4 specularColor = vec4(0.6,0.6,0.6, 0.);
	float shininess = 1.5;      
	
	// fresnel factor between two diffuse colors
	float fresnelColorShininess = 5.0;

	// scaling of vertex colors (targetColor = (color+brightness)*contrast
	float vertexColorBrightness = -0.75;
	float vertexColorContrast = 4.0;
	
	// texture does is upside down
	vec2 varCoord = _varCoord;
	varCoord.y = 1.0 - varCoord.y;
	
	float normalAlpha = 1.0;

	vec3 normal = _normal;
/*	if (oparam1 > 0.0)
	{
		vec4 temp = texture2D(tex2,  varCoord.xy ).rgba;
		vec3 n = vec3(temp);
		n = n  * 2.0 - 1.0;
		normalAlpha = temp.w;
		
		mat3 tangentMatrix = mat3(_tangent, _binormal, _normal);
		n = tangentMatrix * n;
		
		normal = n;
	}
*/	
	vec4 paintColor = ambientColor + texture2D(tex0, varCoord.xy );;
	
	float NdotV = saturate(dot(normal, _viewDirection));
	float h = pow(NdotV, fresnelColorShininess);
	vec4 diffColor = diffuseColor*h + diffuseColor2*(1.0-h);
	
	vec3 rt = _reflectDir.xzy;
 	rt.y = rt.y*-1.0;
 	vec2 reflectTexCoord = (rt.xy * 0.5 + 0.5);
 	vec4 incomeLight = texture2D(tex2, reflectTexCoord) * shininess;
	paintColor += incomeLight * specularColor + diffColor;
	//paintColor = vec4(reflectTexCoord, 0., 1.);//
	
	// scale the vertex color
	float vertexColor = _vertexColor;
	vertexColor = saturate((vertexColor+vertexColorBrightness)*vertexColorContrast);

						  
	paintColor = paintColor * vertexColor;
	
	paintColor.w *= normalAlpha;
	
//	paintColor.rgb*=1.0;
	paintColor.a *= 0.2;
	gl_FragColor = paintColor;
	
	//gl_FragColor = vec4(normalAlpha, 0., 0., 1.);
} 
